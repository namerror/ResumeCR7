#!/usr/bin/env python3
"""Run selected ResumeCR7 agentic-testing dataset requests."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_DATASET = Path(__file__).with_name("dataset.json")
DEFAULT_TIMEOUT_SECONDS = 120.0
SUITE_ALIASES = {
    "all": "all",
    "skill": "skill_selection",
    "skills": "skill_selection",
    "skill_selection": "skill_selection",
    "project": "project_selection",
    "projects": "project_selection",
    "project_selection": "project_selection",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run selected requests from docs/agentic-testing/dataset.json."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help=f"Dataset path. Default: {DEFAULT_DATASET}",
    )
    parser.add_argument(
        "--base-url",
        help="API base URL. Defaults to the dataset base_url value.",
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=sorted(SUITE_ALIASES),
        help="Suite to run. Repeatable. Use skill_selection, project_selection, or all.",
    )
    parser.add_argument(
        "--input-set",
        action="append",
        dest="input_sets",
        help="Input set id to run. Repeatable. Defaults to every input set in selected suites.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        dest="variants",
        help="Variant id to run. Repeatable. Defaults to every variant in selected input sets.",
    )
    parser.add_argument(
        "--exclude-variant",
        action="append",
        default=[],
        dest="exclude_variants",
        help="Variant id to skip. Repeatable.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON results to this path. If omitted, prints JSON to stdout.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the selected request payloads without sending HTTP requests.",
    )
    parser.add_argument(
        "--no-health",
        action="store_true",
        help="Skip the GET /health request before running selected requests.",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit non-zero if health fails, a request errors, or a response status is >= 400.",
    )
    return parser.parse_args()


def load_dataset(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as dataset_file:
        dataset = json.load(dataset_file)
    if not isinstance(dataset, dict):
        raise ValueError("Dataset root must be a JSON object.")
    return dataset


def selected_suite_keys(dataset: dict[str, Any], requested: list[str] | None) -> list[str]:
    suite_keys = [
        key
        for key, value in dataset.items()
        if isinstance(value, dict) and isinstance(value.get("input_sets"), list)
    ]
    if not requested or "all" in requested:
        return suite_keys

    normalized = []
    for suite in requested:
        suite_key = SUITE_ALIASES[suite]
        if suite_key not in suite_keys:
            raise ValueError(f"Suite {suite_key!r} was not found in the dataset.")
        if suite_key not in normalized:
            normalized.append(suite_key)
    return normalized


def build_payload(base_payload: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(base_payload)
    overrides = {
        key: value
        for key, value in variant.items()
        if key not in {"id", "description", "notes", "payload_overrides"}
    }
    payload.update(overrides)
    payload.update(copy.deepcopy(variant.get("payload_overrides", {})))
    return payload


def iter_requests(
    dataset: dict[str, Any],
    suite_keys: list[str],
    input_filter: set[str] | None,
    variant_filter: set[str] | None,
    excluded_variants: set[str],
) -> list[dict[str, Any]]:
    requests_to_run = []
    for suite_key in suite_keys:
        suite = dataset[suite_key]
        endpoint = suite.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint.startswith("/"):
            raise ValueError(f"Suite {suite_key!r} must define an endpoint like '/select-skills'.")

        for input_set in suite["input_sets"]:
            input_id = input_set.get("id")
            if input_filter and input_id not in input_filter:
                continue
            base_payload = input_set.get("base_payload")
            if not isinstance(base_payload, dict):
                raise ValueError(f"Input set {input_id!r} must define a base_payload object.")

            for variant in input_set.get("variants", []):
                variant_id = variant.get("id")
                if variant_filter and variant_id not in variant_filter:
                    continue
                if variant_id in excluded_variants:
                    continue
                requests_to_run.append(
                    {
                        "suite": suite_key,
                        "endpoint": endpoint,
                        "input_set_id": input_id,
                        "variant_id": variant_id,
                        "review_focus": input_set.get("review_focus"),
                        "expected_review_anchors": input_set.get("expected_review_anchors"),
                        "request": build_payload(base_payload, variant),
                    }
                )
    return requests_to_run


def get_health(base_url: str, timeout: float) -> dict[str, Any]:
    try:
        response = requests.get(f"{base_url}/health", timeout=timeout)
        return {
            "status_code": response.status_code,
            "body": parse_response_body(response),
        }
    except requests.RequestException as exc:
        return {"error": repr(exc)}


def parse_response_body(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def run_request(base_url: str, item: dict[str, Any], timeout: float) -> dict[str, Any]:
    result = dict(item)
    try:
        response = requests.post(
            f"{base_url}{item['endpoint']}",
            json=item["request"],
            timeout=timeout,
        )
        result["status_code"] = response.status_code
        result["response"] = parse_response_body(response)
    except requests.RequestException as exc:
        result["error"] = repr(exc)
    return result


def has_error(results: dict[str, Any]) -> bool:
    health = results.get("health")
    if isinstance(health, dict) and ("error" in health or health.get("status_code", 0) >= 400):
        return True
    for item in results["requests"]:
        if "error" in item or item.get("status_code", 0) >= 400:
            return True
    return False


def main() -> int:
    args = parse_args()
    dataset = load_dataset(args.dataset)
    base_url = (args.base_url or dataset.get("base_url") or "").rstrip("/")
    if not base_url:
        raise ValueError("Provide --base-url or set base_url in the dataset.")

    requested_suites = selected_suite_keys(dataset, args.suite)
    selected = iter_requests(
        dataset=dataset,
        suite_keys=requested_suites,
        input_filter=set(args.input_sets) if args.input_sets else None,
        variant_filter=set(args.variants) if args.variants else None,
        excluded_variants=set(args.exclude_variants),
    )
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset),
        "base_url": base_url,
        "dry_run": args.dry_run,
        "selected_count": len(selected),
        "health": None,
        "requests": selected if args.dry_run else [],
    }

    if not args.dry_run:
        if not args.no_health:
            results["health"] = get_health(base_url, args.timeout)
        results["requests"] = [run_request(base_url, item, args.timeout) for item in selected]

    output = json.dumps(results, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
        print(f"Wrote {len(selected)} request result(s) to {args.output}")
    else:
        print(output)

    if args.fail_on_error and not args.dry_run and has_error(results):
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

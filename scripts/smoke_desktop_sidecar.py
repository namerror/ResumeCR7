from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_desktop_sidecar


BACKEND_HOST = "127.0.0.1"
DEFAULT_TIMEOUT_SECONDS = 30.0
HEALTH_POLL_SECONDS = 0.25


def reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((BACKEND_HOST, 0))
        return int(sock.getsockname()[1])


def health_check_once(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=1.0) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (
        json.JSONDecodeError,
        OSError,
        TimeoutError,
        urllib.error.URLError,
    ):
        return False
    return payload.get("status") == "ok"


def wait_for_health(
    base_url: str,
    *,
    timeout_seconds: float,
    poll_seconds: float = HEALTH_POLL_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if health_check_once(base_url):
            return
        time.sleep(poll_seconds)
    raise TimeoutError(f"Timed out waiting for {base_url}/health")


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def read_finished_output(process: subprocess.Popen[str]) -> str:
    try:
        stdout, stderr = process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        return ""
    return "\n".join(part for part in (stdout, stderr) if part)


def run_sidecar_smoke(
    binary_path: Path,
    *,
    data_dir: Path,
    port: int | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    if not binary_path.exists():
        raise FileNotFoundError(f"Sidecar binary does not exist: {binary_path}")

    selected_port = port or reserve_loopback_port()
    base_url = f"http://{BACKEND_HOST}:{selected_port}"
    data_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "RESUMECR7_PACKAGED": "true",
        "RESUMECR7_DATA_DIR": str(data_dir),
    }
    command = [
        str(binary_path),
        "--host",
        BACKEND_HOST,
        "--port",
        str(selected_port),
        "--packaged",
        "--data-dir",
        str(data_dir),
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = read_finished_output(process)
                raise RuntimeError(
                    f"Sidecar exited before /health became ready "
                    f"(exit code {process.returncode}).\n{output}"
                )
            if health_check_once(base_url):
                return base_url
            time.sleep(HEALTH_POLL_SECONDS)
        raise TimeoutError(f"Timed out waiting for {base_url}/health")
    finally:
        terminate_process(process)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and smoke test the ResumeCR7 desktop backend sidecar."
    )
    parser.add_argument(
        "--binary",
        type=Path,
        help="Use an existing sidecar binary instead of building one first.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Runtime data directory for the smoke run. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Loopback port for the sidecar. Defaults to an available ephemeral port.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Maximum seconds to wait for /health. Defaults to {DEFAULT_TIMEOUT_SECONDS:g}.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    binary_path = args.binary or build_desktop_sidecar.build_sidecar()

    if args.data_dir is not None:
        base_url = run_sidecar_smoke(
            binary_path,
            data_dir=args.data_dir,
            port=args.port,
            timeout_seconds=args.timeout_seconds,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="resumecr7-sidecar-smoke-") as temp_dir:
            base_url = run_sidecar_smoke(
                binary_path,
                data_dir=Path(temp_dir),
                port=args.port,
                timeout_seconds=args.timeout_seconds,
            )

    print(f"Sidecar health check passed: {base_url}/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

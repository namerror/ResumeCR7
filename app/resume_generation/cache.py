from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal

from app.resume_generation.models import ResumeGenerationCacheConfig

_CACHE_VERSION = 1
_SAFE_SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class ResumeGenerationStageCacheResult:
    data: dict[str, Any]
    source: Literal["cache", "http"]
    cache_key: str
    stored: bool = True


class ResumeGenerationStageCache:
    def __init__(
        self,
        root_path: Path | str,
        *,
        force_refresh: bool = False,
    ) -> None:
        self.root_path = Path(root_path)
        self.force_refresh = force_refresh

    @classmethod
    def from_config(
        cls,
        config: ResumeGenerationCacheConfig,
        *,
        config_path: Path | str,
    ) -> "ResumeGenerationStageCache | None":
        if not config.enabled:
            return None

        root_path = (
            Path(config.path)
            if config.path is not None
            else Path(config_path).parent / "cache"
        )
        return cls(root_path, force_refresh=config.force_refresh)

    def get_or_store(
        self,
        *,
        stage: str,
        payload: dict[str, Any],
        fetch: Callable[[], dict[str, Any]],
        cache_payload: dict[str, Any] | None = None,
        namespace: str | None = None,
        should_use_cached: Callable[[dict[str, Any]], bool] | None = None,
        should_store: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        '''
        Load cached data if payload and stage match an existing cache entry. 
        Otherwise, use the provided fetch function and store the result in cache.
        '''

        return self.get_or_store_result(
            stage=stage,
            payload=payload,
            fetch=fetch,
            cache_payload=cache_payload,
            namespace=namespace,
            should_use_cached=should_use_cached,
            should_store=should_store,
        ).data

    def get_or_store_result(
        self,
        *,
        stage: str,
        payload: dict[str, Any],
        fetch: Callable[[], dict[str, Any]],
        cache_payload: dict[str, Any] | None = None,
        namespace: str | None = None,
        should_use_cached: Callable[[dict[str, Any]], bool] | None = None,
        should_store: Callable[[dict[str, Any]], bool] | None = None,
    ) -> ResumeGenerationStageCacheResult:
        cache_key = self.cache_key(
            stage=stage,
            payload=cache_payload if cache_payload is not None else payload,
        )
        path = self._entry_path(stage=stage, cache_key=cache_key, namespace=namespace)

        if not self.force_refresh:
            cached_data = self._read(path=path, stage=stage, cache_key=cache_key)
            if cached_data is not None and (
                should_use_cached is None or should_use_cached(cached_data)
            ):
                return ResumeGenerationStageCacheResult(
                    data=cached_data,
                    source="cache",
                    cache_key=cache_key,
                )

        data = fetch()
        stored = should_store(data) if should_store is not None else True
        if stored:
            self._write(path=path, stage=stage, cache_key=cache_key, data=data)
        return ResumeGenerationStageCacheResult(
            data=data,
            source="http",
            cache_key=cache_key,
            stored=stored,
        )

    async def get_or_store_result_async(
        self,
        *,
        stage: str,
        payload: dict[str, Any],
        fetch: Callable[[], Awaitable[dict[str, Any]]],
        cache_payload: dict[str, Any] | None = None,
        namespace: str | None = None,
        should_use_cached: Callable[[dict[str, Any]], bool] | None = None,
        should_store: Callable[[dict[str, Any]], bool] | None = None,
    ) -> ResumeGenerationStageCacheResult:
        cache_key = self.cache_key(
            stage=stage,
            payload=cache_payload if cache_payload is not None else payload,
        )
        path = self._entry_path(stage=stage, cache_key=cache_key, namespace=namespace)

        if not self.force_refresh:
            cached_data = self._read(path=path, stage=stage, cache_key=cache_key)
            if cached_data is not None and (
                should_use_cached is None or should_use_cached(cached_data)
            ):
                return ResumeGenerationStageCacheResult(
                    data=cached_data,
                    source="cache",
                    cache_key=cache_key,
                )

        data = await fetch()
        stored = should_store(data) if should_store is not None else True
        if stored:
            self._write(path=path, stage=stage, cache_key=cache_key, data=data)
        return ResumeGenerationStageCacheResult(
            data=data,
            source="http",
            cache_key=cache_key,
            stored=stored,
        )

    def cache_key(self, *, stage: str, payload: dict[str, Any]) -> str:
        canonical_payload = json.dumps(
            {"stage": stage, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    def _entry_path(
        self,
        *,
        stage: str,
        cache_key: str,
        namespace: str | None = None,
    ) -> Path:
        parts = [self.root_path, self._safe_segment(stage)]
        if namespace is not None:
            parts.append(self._safe_segment(namespace))
        return Path(*parts) / f"{cache_key}.json"

    def _read(self, *, path: Path, stage: str, cache_key: str) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                entry = json.load(handle)
        except (FileNotFoundError, JSONDecodeError, OSError):
            return None

        if not isinstance(entry, dict):
            return None
        if entry.get("version") != _CACHE_VERSION:
            return None
        if entry.get("stage") != stage:
            return None
        if entry.get("cache_key") != cache_key:
            return None

        data = entry.get("data")
        return data if isinstance(data, dict) else None

    def _write(
        self,
        *,
        path: Path,
        stage: str,
        cache_key: str,
        data: dict[str, Any],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        payload = {
            "version": _CACHE_VERSION,
            "stage": stage,
            "cache_key": cache_key,
            "data": data,
        }
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
        os.replace(tmp_path, path)

    def _safe_segment(self, value: str) -> str:
        normalized = _SAFE_SEGMENT_PATTERN.sub("_", value.strip()).strip("._")
        if normalized:
            return normalized
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

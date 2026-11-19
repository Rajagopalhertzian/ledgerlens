"""Disk-based cache for LLM responses.

Keyed by request hash (SHA-256 of serialized request).
Supports TTL and size limits.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import xxhash
from filelock import FileLock


@dataclass(frozen=True)
class CacheKey:
    """Cache key for LLM requests."""

    value: str


@dataclass
class CacheEntry:
    """Cache entry with metadata."""

    data: dict[str, Any]
    created_at: float
    accessed_at: float
    hit_count: int = 0


class DiskCache:
    """Disk-based cache with TTL and LRU eviction.

    Uses xxhash for fast filename generation.
    Thread-safe with file locks.
    """

    def __init__(
        self,
        cache_dir: str = "data/llm_cache",
        max_size_mb: int = 500,
        default_ttl_seconds: int = 86400 * 7,  # 7 days
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.default_ttl = default_ttl_seconds
        self._index_path = self.cache_dir / "index.json"
        self._lock_path = self.cache_dir / "index.lock"
        self._index: dict[str, dict[str, Any]] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load cache index from disk."""
        if self._index_path.exists():
            try:
                with self._index_path.open() as f:
                    self._index = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._index = {}

    def _save_index(self) -> None:
        """Save cache index to disk atomically."""
        temp_path = self._index_path.with_suffix(".tmp")
        try:
            with temp_path.open("w") as f:
                json.dump(self._index, f)
            temp_path.replace(self._index_path)
        except OSError:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _get_file_path(self, key: CacheKey) -> Path:
        """Get file path for cache key."""
        # Use xxhash for shorter, filesystem-safe filenames
        filename = xxhash.xxh64(key.value.encode()).hexdigest() + ".json"
        return self.cache_dir / filename

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache exceeds max size."""
        total_size = sum(entry.get("size", 0) for entry in self._index.values())
        if total_size <= self.max_size_bytes:
            return

        # Sort by last accessed time (LRU)
        sorted_entries = sorted(self._index.items(), key=lambda x: x[1].get("accessed_at", 0))

        for key, entry in sorted_entries:
            if total_size <= self.max_size_bytes * 0.8:  # Evict to 80%
                break
            file_path = self._get_file_path(CacheKey(key))
            if file_path.exists():
                file_path.unlink()
            total_size -= entry.get("size", 0)
            del self._index[key]

        self._save_index()

    def _is_expired(self, entry: dict[str, Any]) -> bool:
        """Check if cache entry is expired."""
        created = entry.get("created_at", 0)
        ttl = entry.get("ttl", self.default_ttl)
        return time.time() - created > ttl

    async def get(self, key: CacheKey) -> dict[str, Any] | None:
        """Get cached value by key."""
        lock = FileLock(str(self._lock_path), timeout=5)
        with lock:
            if key.value not in self._index:
                return None

            entry_meta = self._index[key.value]

            # Check expiration
            if self._is_expired(entry_meta):
                await self._delete_entry(key)
                return None

            file_path = self._get_file_path(key)
            if not file_path.exists():
                del self._index[key.value]
                self._save_index()
                return None

            try:
                with file_path.open() as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                await self._delete_entry(key)
                return None
            else:
                # Update access time and hit count
                entry_meta["accessed_at"] = time.time()
                entry_meta["hit_count"] = entry_meta.get("hit_count", 0) + 1
                self._save_index()
                return data

    async def set(self, key: CacheKey, data: dict[str, Any], ttl: int | None = None) -> None:
        """Set cache value with optional TTL."""
        lock = FileLock(str(self._lock_path), timeout=5)
        with lock:
            file_path = self._get_file_path(key)

            # Write data file
            try:
                with file_path.open("w") as f:
                    json.dump(data, f, separators=(",", ":"))
            except OSError as e:
                msg = f"Failed to write cache file: {e}"
                raise RuntimeError(msg) from e

            # Update index
            file_size = file_path.stat().st_size
            now = time.time()
            self._index[key.value] = {
                "created_at": now,
                "accessed_at": now,
                "hit_count": 0,
                "size": file_size,
                "ttl": ttl or self.default_ttl,
            }

            self._save_index()
            self._evict_if_needed()

    async def _delete_entry(self, key: CacheKey) -> None:
        """Delete cache entry."""
        file_path = self._get_file_path(key)
        if file_path.exists():
            file_path.unlink(missing_ok=True)
        if key.value in self._index:
            del self._index[key.value]
        self._save_index()

    async def delete(self, key: CacheKey) -> bool:
        """Delete cache entry by key."""
        lock = FileLock(str(self._lock_path), timeout=5)
        with lock:
            if key.value in self._index:
                await self._delete_entry(key)
                return True
            return False

    async def clear(self) -> int:
        """Clear all cache entries. Returns count of deleted entries."""
        lock = FileLock(str(self._lock_path), timeout=5)
        with lock:
            count = len(self._index)
            for key in self._index:
                file_path = self._get_file_path(CacheKey(key))
                file_path.unlink(missing_ok=True)
            self._index.clear()
            self._save_index()
            return count

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_size = sum(entry.get("size", 0) for entry in self._index.values())
        total_hits = sum(entry.get("hit_count", 0) for entry in self._index.values())
        return {
            "entries": len(self._index),
            "total_size_mb": total_size / (1024 * 1024),
            "max_size_mb": self.max_size_bytes / (1024 * 1024),
            "total_hits": total_hits,
            "hit_rate": total_hits / max(len(self._index), 1),
        }

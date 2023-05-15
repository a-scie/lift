# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import atexit
import hashlib
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, TypeAlias

from appdirs import user_cache_dir
from filelock import FileLock


@dataclass(frozen=True)
class Complete:
    path: Path


@dataclass(frozen=True)
class Missing:
    path: Path
    work: Path


CacheResult: TypeAlias = Complete | Missing


_TTL_EXPIRY_FORMAT = "%m/%d/%y %H:%M:%S"


@dataclass(frozen=True)
class DownloadCache:
    base_dir: Path

    @contextmanager
    def get_or_create(self, url: str, ttl: timedelta | None = None) -> Iterator[CacheResult]:
        """A context manager that yields a `cache result.

        If the cache result is `Missing`, the block yielded to should materialize the given url
        to the `Missing.work` path. Upon successful exit from this context manager, the given url's
        content will exist at the cache result path.
        """
        cached_file = self.base_dir / hashlib.sha256(url.encode()).hexdigest()

        ttl_file = cached_file.with_suffix(".ttl") if ttl else None
        if ttl_file and not ttl_file.exists():
            cached_file.unlink(missing_ok=True)
        elif ttl_file:
            try:
                datetime_object = datetime.strptime(
                    ttl_file.read_text().strip(), _TTL_EXPIRY_FORMAT
                )
                if datetime.now() > datetime_object:
                    cached_file.unlink(missing_ok=True)
            except ValueError:
                cached_file.unlink(missing_ok=True)

        if cached_file.exists():
            yield Complete(path=cached_file)
            return

        cached_file.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(cached_file.with_name(f"{cached_file.name}.lck"))):
            if cached_file.exists():
                yield Complete(path=cached_file)
                return

            work = cached_file.with_name(f"{cached_file.name}.work")
            work.unlink(missing_ok=True)
            atexit.register(work.unlink, missing_ok=True)
            yield Missing(path=cached_file, work=work)
            work.rename(cached_file)
            if ttl_file and ttl:
                ttl_file.write_text((datetime.now() + ttl).strftime(_TTL_EXPIRY_FORMAT))


def science_cache() -> Path:
    return Path(os.environ.get("SCIENCE_CACHE", user_cache_dir("science")))


def download_cache() -> DownloadCache:
    return DownloadCache(science_cache() / "downloads")

# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import atexit
import errno
import hashlib
import os
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Iterator, TypeAlias

from filelock import FileLock

from science.context import ScienceConfig
from science.model import Url


def _delete_dir(directory: Path) -> None:
    delete_directory = directory.with_suffix(f".{uuid.uuid4().hex}")
    try:
        directory.rename(delete_directory)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    else:
        shutil.rmtree(delete_directory, ignore_errors=True)


@dataclass(frozen=True)
class CacheEntry:
    _PRIMARY_SUBDIR: ClassVar[str] = "_"

    # N.B.: aux is a reserved word in Windows path names; so we avoid it.
    # See: https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file#naming-conventions
    _AUX_SUBDIR: ClassVar[str] = "+"

    _cache_dir: Path
    _file: str

    @property
    def path(self) -> Path:
        return self._cache_dir / self._PRIMARY_SUBDIR / self._file

    @property
    def aux_dir(self) -> Path:
        return self._cache_dir / self._AUX_SUBDIR

    def delete(self) -> None:
        _delete_dir(self._cache_dir)


@dataclass(frozen=True)
class Complete(CacheEntry):
    pass


@dataclass(frozen=True)
class Missing(CacheEntry):
    _work_dir: Path

    @cached_property
    def work_path(self) -> Path:
        work_dir = self._work_dir / self._PRIMARY_SUBDIR
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir / self._file

    @cached_property
    def work_aux_dir(self) -> Path:
        work_aux_dir = self._work_dir / self._AUX_SUBDIR
        work_aux_dir.mkdir(parents=True, exist_ok=True)
        return work_aux_dir


CacheResult: TypeAlias = Complete | Missing


_TTL_EXPIRY_FORMAT = "%m/%d/%y %H:%M:%S"


@dataclass(frozen=True)
class DownloadCache:
    # Bump this when changing download cache on-disk structure.
    _VERSION: ClassVar[int] = 1

    base_dir: Path

    @contextmanager
    def get_or_create(self, url: Url, ttl: timedelta | None = None) -> Iterator[CacheResult]:
        """A context manager that yields a cache result.

        If the cache result is `Missing`, the block yielded to should materialize the given url to
        the `Missing.work_path` path. Upon successful exit from this context manager, the given
        url's content will exist at the cache result path.

        Auxiliary files and directories can be created using `Missing.work_aux_dir` as a base.
        Anything created under that directory will be made available atomically at the cache result
        aux dir.
        """

        # Cache structure looks like so for a cached entry:
        # ---
        # <base_dir>/1/abcd1234.lck
        # <base_dir>/1/abcd1234.ttl
        # <base_dir>/1/abcd1234/
        #     _/file
        #     aux/ (This directory tree is only present if Missing.work_aux_dir is used by caller.)
        #
        # For in-flight cache entry creation, you'll find:
        # ---
        # <base_dir>/1/abcd1234.lck
        # <base_dir>/1/abcd1234.work/
        #     _/file
        #     aux/ (Again, only present if Missing.work_aux_dir is used by caller.)

        url_hash = hashlib.sha256(url.encode()).hexdigest()
        cache_dir = self.base_dir / str(self._VERSION) / url_hash

        ttl_file = cache_dir.with_suffix(".ttl") if ttl else None
        if ttl_file and not ttl_file.exists():
            _delete_dir(cache_dir)
        elif ttl_file:
            try:
                datetime_object = datetime.strptime(
                    ttl_file.read_text().strip(), _TTL_EXPIRY_FORMAT
                )
                if datetime.now() > datetime_object:
                    _delete_dir(cache_dir)
            except ValueError:
                _delete_dir(cache_dir)

        cache_file = os.path.basename(url.info.path)

        if cache_dir.exists():
            yield Complete(_cache_dir=cache_dir, _file=cache_file)
            return

        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(cache_dir.with_name(f"{cache_dir.name}.lck"))):
            if cache_dir.exists():
                yield Complete(_cache_dir=cache_dir, _file=cache_file)
                return

            work_dir = cache_dir.with_name(f"{cache_dir.name}.work")
            _delete_dir(work_dir)
            atexit.register(_delete_dir, work_dir)
            yield Missing(_cache_dir=cache_dir, _file=cache_file, _work_dir=work_dir)
            work_dir.rename(cache_dir)
            if ttl_file and ttl:
                ttl_file.write_text((datetime.now() + ttl).strftime(_TTL_EXPIRY_FORMAT))


def science_cache() -> Path:
    return ScienceConfig.active().cache_dir


def download_cache() -> DownloadCache:
    return DownloadCache(science_cache() / "downloads")

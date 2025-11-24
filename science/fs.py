# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).


import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from science.cache import science_cache

_TMP_BASE_DIR = science_cache() / ".tmp"


@contextmanager
def temporary_directory(prefix: str, delete: bool = True) -> Iterator[Path]:
    _TMP_BASE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=_TMP_BASE_DIR,
        prefix=prefix if prefix.endswith(".") else f"{prefix}.",
        delete=delete,
        ignore_cleanup_errors=True,
    ) as td:
        yield Path(td)

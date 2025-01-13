# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import atexit
import shutil
import tempfile
from pathlib import Path

from setuptools import setup

_BUILD_DIR: Path | None = None


def ensure_unique_build_dir() -> Path:
    global _BUILD_DIR
    if _BUILD_DIR is None:
        _build_dir = Path(tempfile.mkdtemp(prefix="science-dist-build."))
        atexit.register(shutil.rmtree, _build_dir, ignore_errors=True)
        _BUILD_DIR = _build_dir
    return _BUILD_DIR


def unique_build_dir(name) -> str:
    path = ensure_unique_build_dir() / name
    path.mkdir()
    return str(path)


if __name__ == "__main__":
    setup(
        # The `egg_info --egg-base`, `build --build-base` and `bdist_wheel --bdist-dir` setup.py
        # sub-command options we pass below work around the otherwise default `<CWD>/build/`
        # directory for all three which defeats concurrency in tests.
        options={
            "egg_info": {"egg_base": unique_build_dir("egg_base")},
            "build": {"build_base": unique_build_dir("build_base")},
            "bdist_wheel": {"bdist_dir": unique_build_dir("bdist_dir")},
        }
    )

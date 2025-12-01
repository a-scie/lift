# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os
import sys
from pathlib import Path
from typing import Iterator

import pytest
from click import Command, Context
from click.globals import pop_context, push_context

from science.context import ScienceConfig
from science.platform import CURRENT_PLATFORM, CURRENT_PLATFORM_SPEC, Platform, PlatformSpec


def pytest_sessionstart(session: pytest.Session) -> None:
    sys.path.append(os.path.join(session.config.rootpath, "test-support"))


@pytest.fixture(scope="session")
def build_root() -> Path:
    try:
        return Path(os.environ["BUILD_ROOT"]).resolve()
    except KeyError:
        pytest.fail("Tests must be run via `uv run dev-cmd` or `uv run dev-cmd test`.")


@pytest.fixture(scope="session")
def science_pyz() -> Path:
    try:
        return Path(os.environ["SCIENCE_TEST_PYZ_PATH"]).resolve()
    except KeyError:
        pytest.fail("Tests must be run via `uv run dev-cmd` or `uv run dev-cmd test`.")


@pytest.fixture
def cache_dir(tmp_path: Path) -> Iterator[Path]:
    cache_dir = tmp_path / "nce"
    push_context(Context(Command(None), obj=ScienceConfig(cache_dir=cache_dir)))
    try:
        yield cache_dir
    finally:
        pop_context()


@pytest.fixture
def current_platform() -> Platform:
    return CURRENT_PLATFORM


@pytest.fixture
def current_platform_spec() -> PlatformSpec:
    return CURRENT_PLATFORM_SPEC

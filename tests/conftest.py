# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def build_root() -> Path:
    try:
        return Path(os.environ["BUILD_ROOT"])
    except KeyError:
        pytest.fail("Tests must be run via `nox` or `nox -etest`.")


@pytest.fixture(scope="session")
def science_pyz() -> Path:
    try:
        return Path(os.environ["SCIENCE_TEST_PYZ_PATH"])
    except KeyError:
        pytest.fail("Test must be run via `nox` or `nox -etest`.")

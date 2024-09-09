# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import subprocess
from pathlib import Path

import pytest
from _pytest.tmpdir import TempPathFactory

from science.os import IS_WINDOWS


@pytest.fixture(scope="module")
def installer(build_root: Path) -> list:
    if IS_WINDOWS:
        return ["pwsh", build_root / "install.ps1", "-NoModifyPath"]
    else:
        return [build_root / "install.sh"]


def run_captured(cmd: list):
    return subprocess.run(cmd, capture_output=True, text=True)


def test_installer_help(installer: list):
    """Validates help in the installer."""
    long_help = "-Help" if IS_WINDOWS else "--help"
    for tested_flag in ("-h", long_help):
        assert (result := run_captured(installer + [tested_flag])).returncode == 0
        assert long_help in result.stdout, f"Expected '{long_help}' in tool output"


def test_installer_fetch_latest(tmp_path_factory: TempPathFactory, installer: list):
    """Invokes install.sh to fetch the latest science release binary, then invokes it."""
    test_dir = tmp_path_factory.mktemp("install-test-default")
    bin_dir = test_dir / "bin"

    assert (result := run_captured(installer + ["-d", bin_dir])).returncode == 0
    assert (
        "success" in result.stdout if IS_WINDOWS else result.stderr
    ), "Expected 'success' in tool stderr logging"

    assert (result := run_captured([bin_dir / "science", "-V"])).returncode == 0
    assert result.stdout.strip(), "Expected version output in tool stdout"


def test_installer_fetch_argtest(tmp_path_factory: TempPathFactory, installer: list):
    """Exercises all the options in the installer."""
    test_dir = tmp_path_factory.mktemp("install-test")
    test_ver = "0.7.0"
    bin_dir = test_dir / "bin"

    assert (result := run_captured(installer + ["-V", test_ver, "-d", bin_dir])).returncode == 0
    output = result.stdout if IS_WINDOWS else result.stderr
    assert "success" in output, "Expected 'success' in tool stderr logging"

    # Ensure missing $PATH entry warning (assumes our temp dir by nature is not on $PATH).
    assert "is not detected on $PATH" in output, "Expected missing $PATH entry warning"

    # Check expected versioned binary exists.
    assert (result := run_captured([bin_dir / "science", "-V"])).returncode == 0
    assert (
        result.stdout.strip() == test_ver
    ), f"Expected version output in tool stdout to be {test_ver}"

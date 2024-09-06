# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import subprocess
from pathlib import Path

import pytest
from _pytest.tmpdir import TempPathFactory

from science.os import IS_WINDOWS


@pytest.fixture(scope="module")
def installer(build_root: Path) -> list:
    installer = build_root / "install.sh"
    return ["bash", installer] if IS_WINDOWS else [installer]


def run_captured(cmd: list):
    return subprocess.run(cmd, capture_output=True, text=True)


def test_installer_help(installer: list):
    """Validates -h|--help in the installer."""
    for tested_flag in ("-h", "--help"):
        assert (result := run_captured(installer + [tested_flag])).returncode == 0
        assert "--help" in result.stdout, "Expected '--help' in tool output"


def test_installer_fetch_latest(tmp_path_factory: TempPathFactory, installer: list):
    """Invokes install.sh to fetch the latest science release binary, then invokes it."""
    test_dir = tmp_path_factory.mktemp("install-test-default")

    assert (result := run_captured(installer + ["-d", f"{test_dir}/bin"])).returncode == 0
    assert "success" in result.stderr, "Expected 'success' in tool stderr logging"

    assert (result := run_captured([f"{test_dir}/bin/science", "-V"])).returncode == 0
    assert result.stdout.strip(), "Expected version output in tool stdout"


def test_installer_fetch_argtest(tmp_path_factory: TempPathFactory, installer: list):
    """Exercises all the options in the installer."""
    test_dir = tmp_path_factory.mktemp("install-test")
    test_ver = "0.6.1"

    assert (
        result := run_captured(
            installer + ["-V", test_ver, "-b", f"science{test_ver}", "-d", f"{test_dir}/bin"]
        )
    ).returncode == 0
    assert "success" in result.stderr, "Expected 'success' in tool stderr logging"

    # Ensure missing $PATH entry warning (assumes our temp dir by nature is not on $PATH).
    assert (
        f"WARNING: {test_dir}/bin is not detected on $PATH" in result.stderr
    ), "Expected missing $PATH entry warning"

    # Check expected versioned binary exists.
    assert (result := run_captured([f"{test_dir}/bin/science{test_ver}", "-V"])).returncode == 0
    assert (
        result.stdout.strip() == test_ver
    ), f"Expected version output in tool stdout to be {test_ver}"

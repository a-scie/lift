# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import shutil
import subprocess
from pathlib import Path, PurePath

import pytest
from _pytest.tmpdir import TempPathFactory

from science.os import IS_WINDOWS


@pytest.fixture(scope="module")
def installer(build_root: Path) -> list:
    installer = build_root / "install.sh"
    if IS_WINDOWS:
        # TODO(John Sirois): Get rid of all this shenanigans and write an install.ps1 instead:
        #  https://github.com/a-scie/lift/issues/91

        # Given a git for Windows install at C:\Program Files\Git, we will find the git executable
        # at one of these two locations:
        # + Running under cmd or pwsh, etc.: C:\Program Files\Git\cmd\git.EXE
        # + Running under git bash:          C:\Program Files\Git\mingw64\bin\git.EXE
        # We expect the msys2 root to be at the git for Windows install root, which is
        # C:\Program Files\Git in this case.
        assert (git := shutil.which("git")) is not None, "This test requires Git bash on Windows."
        msys2_root = PurePath(git).parent.parent
        if "mingw64" == msys2_root.name:
            msys2_root = msys2_root.parent

        assert (bash := shutil.which("bash", path=msys2_root / "usr" / "bin")) is not None, (
            f"The git executable at {git} does not appear to have msys2 root at the expected path "
            f"of {msys2_root}."
        )
        return [bash, installer]
    else:
        return [installer]


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
    bin_dir = test_dir / "bin"

    assert (result := run_captured(installer + ["-d", bin_dir])).returncode == 0
    assert "success" in result.stderr, "Expected 'success' in tool stderr logging"

    assert (result := run_captured([bin_dir / "science", "-V"])).returncode == 0
    assert result.stdout.strip(), "Expected version output in tool stdout"


def test_installer_fetch_argtest(tmp_path_factory: TempPathFactory, installer: list):
    """Exercises all the options in the installer."""
    test_dir = tmp_path_factory.mktemp("install-test")
    test_ver = "0.7.0"
    bin_dir = test_dir / "bin"
    bin_file = f"science{test_ver}"

    assert (
        result := run_captured(installer + ["-V", test_ver, "-b", bin_file, "-d", bin_dir])
    ).returncode == 0
    assert "success" in result.stderr, "Expected 'success' in tool stderr logging"

    # Ensure missing $PATH entry warning (assumes our temp dir by nature is not on $PATH).
    assert "is not detected on $PATH" in result.stderr, "Expected missing $PATH entry warning"

    # Check expected versioned binary exists.
    assert (result := run_captured([bin_dir / bin_file, "-V"])).returncode == 0
    assert (
        result.stdout.strip() == test_ver
    ), f"Expected version output in tool stdout to be {test_ver}"

# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import subprocess

from _pytest.tmpdir import TempPathFactory

INSTALLER = "./install.sh"


def test_installer_help():
    """Validates -h|--help in the installer."""
    assert "--help" in subprocess.check_output([INSTALLER, "-h"]).decode("utf-8")
    assert "--help" in subprocess.check_output([INSTALLER, "--help"]).decode("utf-8")


def test_installer_fetch_latest(tmp_path_factory: TempPathFactory):
    """Invokes install.sh to fetch the latest science release binary, then invokes it."""
    test_dir = tmp_path_factory.mktemp("install-test-default")
    assert "success" in subprocess.check_output(
        [INSTALLER, "-d", f"{test_dir}/bin"],
        stderr=subprocess.STDOUT,
    ).decode("utf-8")
    assert subprocess.check_output([f"{test_dir}/bin/science", "-V"]).strip()


def test_installer_fetch_argtest(tmp_path_factory: TempPathFactory):
    """Exercises all the options in the installer."""
    test_dir = tmp_path_factory.mktemp("install-test")
    output = subprocess.check_output(
        [INSTALLER, "-V", "0.6.1", "-b", "science061", "-d", f"{test_dir}/bin"],
        stderr=subprocess.STDOUT,
    ).decode("utf-8")
    assert "success" in output

    # Ensure missing $PATH entry warning.
    assert f"WARNING: {test_dir}/bin is not detected on $PATH" in output

    # Check expected versioned binary exists.
    assert (
        subprocess.check_output([f"{test_dir}/bin/science061", "-V"]).decode("utf-8").strip()
        == "0.6.1"
    )

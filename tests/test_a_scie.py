# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import subprocess

from _pytest.tmpdir import TempPathFactory
from packaging import version

from science import a_scie
from science.model import Ptex


def test_ptex_latest(tmp_path_factory: TempPathFactory) -> None:
    latest = a_scie.ptex()
    subprocess.run(args=[latest.path, "-V"], check=True)


def test_ptex_version(tmp_path_factory: TempPathFactory) -> None:
    ptex_versioned = a_scie.ptex(specification=Ptex(version=version.parse("1.7.0")))
    assert (
        "1.7.0"
        == subprocess.run(
            args=[ptex_versioned.path, "-V"], stdout=subprocess.PIPE, text=True, check=True
        ).stdout.strip()
    )

# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import subprocess

from _pytest.tmpdir import TempPathFactory

from science import a_scie


def test_ptex_latest(tmp_path_factory: TempPathFactory) -> None:
    dest_dir = tmp_path_factory.mktemp("staging")
    latest = a_scie.ptex(dest_dir=dest_dir)
    subprocess.run(args=[str(dest_dir / latest.name), "-V"], check=True)


def test_ptex_version(tmp_path_factory: TempPathFactory) -> None:
    dest_dir = tmp_path_factory.mktemp("staging")
    latest = a_scie.ptex(dest_dir=dest_dir, version="0.6.0")
    assert (
        "0.6.0"
        == subprocess.run(
            args=[str(dest_dir / latest.name), "-V"], stdout=subprocess.PIPE, text=True, check=True
        ).stdout.strip()
    )

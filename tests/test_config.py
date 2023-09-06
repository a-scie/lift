# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import json
import os.path
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from science.config import parse_config_file
from science.model import Identifier
from science.platform import Platform


def test_parse(build_root: Path) -> None:
    app = parse_config_file(build_root / "lift.toml")
    interpreters = list(app.interpreters)
    assert 1 == len(interpreters), "Expected science to ship on a single fixed interpreter."

    interpreter = interpreters[0]
    distribution = interpreter.provider.distribution(Platform.current())
    assert (
        distribution is not None
    ), "Expected a Python interpreter distribution to be available for each platform tests run on."
    assert (
        distribution.file.source and distribution.file.source.lazy
    ), "Expected science to ship as a gouged-out binary."
    assert (
        Identifier("python") in distribution.placeholders
    ), "Expected the Python interpreter to expose a 'python' placeholder for its `python` binary."


def test_interpreter_groups(tmp_path: Path, science_pyz: Path) -> None:
    with resources.as_file(resources.files("data") / "interpreter-groups.toml") as config:
        subprocess.run(
            args=[
                sys.executable,
                str(science_pyz),
                "lift",
                "build",
                "--dest-dir",
                str(tmp_path),
                config,
            ],
            check=True,
        )

        exe_path = tmp_path / Platform.current().binary_name("igs")
        subprocess.run(args=[exe_path], env={**os.environ, "SCIE": "inspect"}, check=True)

        scie_base = tmp_path / "scie-base"

        data1 = json.loads(
            subprocess.run(
                args=[exe_path],
                env={**os.environ, "PYTHON": "cpython310", "SCIE_BASE": str(scie_base)},
                stdout=subprocess.PIPE,
                check=True,
            ).stdout
        )
        assert [3, 10] == data1["version"]
        assert (scie_base / data1["hash"]).is_dir()

        data2 = json.loads(
            subprocess.run(
                args=[exe_path],
                env={**os.environ, "PYTHON": "cpython311", "SCIE_BASE": str(scie_base)},
                stdout=subprocess.PIPE,
                check=True,
            ).stdout
        )
        assert [3, 11] == data2["version"]
        assert (scie_base / data2["hash"]).is_dir()

        assert data1["hash"] != data2["hash"]


def test_scie_base(tmp_path: Path, science_pyz: Path) -> None:
    current_platform = Platform.current()
    match current_platform:
        case Platform.Windows_x86_64:
            config_name = "scie-base.windows.toml"
            expected_base = "~\\AppData\\Local\\Temp\\custom-base"
        case _:
            config_name = "scie-base.unix.toml"
            expected_base = "/tmp/custom-base"

    with resources.as_file(resources.files("data") / config_name) as config:
        subprocess.run(
            args=[
                sys.executable,
                str(science_pyz),
                "lift",
                "build",
                "--dest-dir",
                str(tmp_path),
                config,
            ],
            check=True,
        )

        exe_path = tmp_path / current_platform.binary_name("custom-base")

        data = json.loads(
            subprocess.run(
                args=[exe_path],
                env={**os.environ, "SCIE": "inspect"},
                stdout=subprocess.PIPE,
                check=True,
            ).stdout
        )
        assert expected_base == data["scie"]["lift"]["base"]
        expanded_base = os.path.expanduser(expected_base)
        try:
            assert (
                f"Hello from {expanded_base}!"
                == subprocess.run(
                    args=[exe_path], stdout=subprocess.PIPE, text=True, check=True
                ).stdout.strip()
            )
        finally:
            shutil.rmtree(expanded_base, ignore_errors=True)

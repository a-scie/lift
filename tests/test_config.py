# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import json
import os.path
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from textwrap import dedent

import pytest

from science.config import parse_config_file
from science.model import Identifier
from science.platform import (
    CURRENT_PLATFORM,
    CURRENT_PLATFORM_SPEC,
    LibC,
    Os,
    Platform,
    PlatformSpec,
)


def test_parse(build_root: Path) -> None:
    app = parse_config_file(build_root / "lift.toml")
    interpreters = list(app.interpreters)
    assert 1 == len(interpreters), "Expected science to ship on a single fixed interpreter."

    interpreter = interpreters[0]
    distribution = interpreter.provider.distribution(CURRENT_PLATFORM_SPEC)
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

        exe_path = tmp_path / CURRENT_PLATFORM.binary_name("igs")
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
    current_platform = CURRENT_PLATFORM
    if current_platform.is_windows:
        config_name = "scie-base.windows.toml"
        expected_base = "~\\AppData\\Local\\Temp\\custom-base"
    else:
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

        # Ensure our configured scie base is not over-ridden.
        env = os.environ.copy()
        env.pop("SCIE_BASE", None)
        try:
            assert (
                f"Hello from {expanded_base}!"
                == subprocess.run(
                    args=[exe_path], env=env, stdout=subprocess.PIPE, text=True, check=True
                ).stdout.strip()
            )
        finally:
            shutil.rmtree(expanded_base, ignore_errors=True)


def test_command_descriptions(tmp_path: Path, science_pyz: Path) -> None:
    with resources.as_file(resources.files("data") / "command-descriptions.toml") as config:
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

        exe_path = tmp_path / CURRENT_PLATFORM.binary_name("command-descriptions")
        scie_base = tmp_path / "scie-base"
        data = json.loads(
            subprocess.run(
                args=[exe_path],
                env={**os.environ, "SCIE_BASE": str(scie_base)},
                stdout=subprocess.PIPE,
                check=True,
            ).stdout
        )
        assert {"": "Print a JSON object of command descriptions by name.", "version": None} == data


def test_unrecognized_config_fields(tmp_path: Path, science_pyz: Path) -> None:
    with resources.as_file(resources.files("data") / "unrecognized-config-fields.toml") as config:
        result = subprocess.run(
            args=[
                sys.executable,
                str(science_pyz),
                "lift",
                "build",
                "--dest-dir",
                str(tmp_path),
                config,
            ],
            text=True,
            stderr=subprocess.PIPE,
        )
        assert result.returncode != 0
        assert (
            dedent(
                f"""\
                The following `lift` manifest entries in {config} were not recognized (indexes are 1-based):
                                 scie-jump: Did you mean scie_jump?
                        scie_jump.version2: Did you mean version?
                     interpreters[2].lizzy: Did you mean lazy?
                    commands[1].just_wrong
                commands[1].env.remove_re2: Did you mean remove_re or remove_exact?
                  commands[1].env.replace2: Did you mean replace?
                                  app-info: Did you mean app_info?

                Refer to the lift manifest format specification at https://science.scie.app/manifest.html or by running `science doc open manifest`.
                """
            )
            == result.stderr
        )


def test_platform_specs() -> None:
    with resources.as_file(resources.files("data") / "platform-specs.toml") as config:
        app = parse_config_file(config)
        assert (
            frozenset(
                (
                    PlatformSpec(Platform.Linux_aarch64),
                    PlatformSpec(Platform.Linux_armv7l),
                    PlatformSpec(Platform.Linux_powerpc64le),
                    PlatformSpec(Platform.Linux_s390x),
                    PlatformSpec(Platform.Linux_x86_64, LibC.GLIBC),
                    PlatformSpec(Platform.Linux_x86_64, LibC.MUSL),
                    PlatformSpec(Platform.Macos_aarch64),
                    PlatformSpec(Platform.Macos_x86_64),
                    PlatformSpec(Platform.Windows_aarch64),
                    PlatformSpec(Platform.Windows_x86_64),
                )
            )
            == app.platform_specs
        )


@pytest.mark.skipif(
    CURRENT_PLATFORM.os is not Os.Linux, reason="This test needs to run a Linux scie."
)
def test_PBS_gnu_and_musl(tmp_path: Path, science_pyz: Path) -> None:
    with resources.as_file(resources.files("data") / "PBS-gnu-and-musl.toml") as config:
        subprocess.run(
            args=[
                sys.executable,
                str(science_pyz),
                "lift",
                "build",
                "--dest-dir",
                str(tmp_path),
                str(config),
            ],
            check=True,
        )
        exe_path = tmp_path / CURRENT_PLATFORM.binary_name("gnu-and-musl")
        scie_base = tmp_path / "scie-base"
        result = subprocess.run(
            args=[exe_path],
            env={**os.environ, "SCIE_BASE": str(scie_base)},
            capture_output=True,
            text=True,
            check=True,
        )
        assert (
            dedent(
                f"""\
                Configured:
                PYTHON=cpython-{CURRENT_PLATFORM_SPEC.libc}
                """
            )
            == result.stderr
        )
        assert "Python 3.13.2\n" == result.stdout

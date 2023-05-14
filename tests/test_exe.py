# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import filecmp
import hashlib
import io
import itertools
import subprocess
import sys
from pathlib import Path
from shutil import which

import pytest
from _pytest.tmpdir import TempPathFactory

from science.platform import Platform


@pytest.fixture(scope="module")
def config(build_root: Path) -> Path:
    return build_root / "lift.toml"


@pytest.fixture(scope="module")
def science_exe(tmp_path_factory: TempPathFactory, build_root: Path, science_pyz: Path) -> Path:
    dest = tmp_path_factory.mktemp("dest")
    subprocess.run(
        args=[
            sys.executable,
            str(science_pyz),
            "build",
            "--file",
            f"science.pyz={science_pyz}",
            "--dest-dir",
            str(dest),
        ],
        check=True,
        cwd=build_root,
    )
    science_exe = dest / Platform.current().binary_name("science")
    assert science_exe.is_file()
    return science_exe


def test_use_platform_suffix(
    tmp_path: Path, science_exe: Path, config: Path, science_pyz: Path
) -> None:
    expected_executable = tmp_path / Platform.current().qualified_binary_name("science")
    assert not expected_executable.exists()
    subprocess.run(
        args=[
            str(science_exe),
            "build",
            "--file",
            f"science.pyz={science_pyz}",
            "--dest-dir",
            str(tmp_path),
            "--use-platform-suffix",
            config,
        ],
        check=True,
    )
    assert expected_executable.is_file()
    assert not (tmp_path / Platform.current().binary_name("science")).exists()


@pytest.fixture(scope="module")
def shasum() -> str | None:
    shasum = which("shasum")
    # N.B.: We check to see if shasum actually works since GH Actions Windows 2022 boxes come with a
    # shasum.BAT on the PATH that runs via a perl.exe not on the PATH leading to error.
    return shasum if shasum and subprocess.run(args=[shasum, "--version"]).returncode == 0 else None


def test_hash(
    tmp_path: Path, science_exe: Path, config: Path, science_pyz: Path, shasum: str | None
) -> None:
    expected_executable = tmp_path / Platform.current().binary_name("science")
    algorithms = "sha1", "sha256", "sha512"
    expected_checksum_paths = [
        Path(f"{expected_executable}.{algorithm}") for algorithm in algorithms
    ]

    for expected_output in expected_executable, *expected_checksum_paths:
        assert not expected_output.exists()

    subprocess.run(
        args=[
            str(science_exe),
            "build",
            "--file",
            f"science.pyz={science_pyz}",
            "--dest-dir",
            str(tmp_path),
            *itertools.chain.from_iterable(("--hash", algorithm) for algorithm in algorithms),
            config,
        ],
        check=True,
    )

    assert expected_executable.is_file()
    if shasum:
        subprocess.run(
            args=[shasum, "-c", *(checksum_file.name for checksum_file in expected_checksum_paths)],
            cwd=str(tmp_path),
            check=True,
        )
    else:
        digests = {
            hashlib.new(checksum_file.suffix.lstrip(".")): checksum_file.read_text().split(" ")[0]
            for checksum_file in expected_checksum_paths
        }
        with expected_executable.open(mode="rb") as fp:
            for chunk in iter(lambda: fp.read(io.DEFAULT_BUFFER_SIZE), b""):
                for actual_digest in digests:
                    actual_digest.update(chunk)
        for actual_digest, expected_value in digests.items():
            assert (
                expected_value == actual_digest.hexdigest()
            ), f"The {actual_digest.name} digest did not match."


def test_dogfood(tmp_path: Path, science_exe: Path, config: Path, science_pyz: Path) -> None:
    dest = tmp_path / "dest"
    subprocess.run(
        args=[
            str(science_exe),
            "build",
            "--file",
            f"science.pyz={science_pyz}",
            "--dest-dir",
            str(dest),
            config,
        ],
        check=True,
    )
    dogfood_science_exe = dest / science_exe.name
    assert dogfood_science_exe.is_file()

    assert science_exe != dogfood_science_exe
    assert filecmp.cmp(science_exe, dogfood_science_exe, shallow=False), (
        "Expected the bootstrap science executable to be able to build itself and produce a "
        "byte-wise identical science executable."
    )

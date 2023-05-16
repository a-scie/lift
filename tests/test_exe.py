# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import filecmp
import hashlib
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from textwrap import dedent
from typing import Any, Iterable

import pytest
import toml
from _pytest.tmpdir import TempPathFactory
from testing import IS_WINDOWS, issue

from science import __version__
from science.config import parse_config_file
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


@issue(2, ignore=True)
def test_nested_filenames(
    _, tmp_path: Path, science_exe: Path, config: Path, science_pyz: Path
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    dest = dist_dir / science_pyz.name
    shutil.copy(science_pyz, dest)

    with config.open(mode="r") as fp:
        config_data = toml.load(fp)
        science_pyz_file = config_data["lift"]["files"][0]
        science_pyz_file["key"] = science_pyz_file["name"]
        science_pyz_file["name"] = str(dest.relative_to(tmp_path))
    test_config = tmp_path / "lift.toml"
    with test_config.open("w") as fp:
        toml.dump(config_data, fp)

    application = parse_config_file(test_config)
    parsed_science_pyz_file = next(iter(application.files))
    assert science_pyz.name == parsed_science_pyz_file.key
    assert str(Path("dist") / science_pyz.name) == parsed_science_pyz_file.name

    dest1 = tmp_path / "dest1"
    subprocess.run(
        args=[str(science_exe), "build", "--dest-dir", str(dest1)], check=True, cwd=tmp_path
    )
    science_exe1 = dest1 / science_exe.name
    assert science_exe1.is_file()
    assert science_exe != science_exe1
    assert not filecmp.cmp(science_exe, science_exe1, shallow=False), (
        "Expected the bootstrap science executable to have different contents from the new "
        "science executable since its manifest changed and the resulting json lift manifest "
        "embedded in the built scie also changed."
    )

    dest2 = tmp_path / "dest2"
    subprocess.run(
        args=[str(science_exe1), "build", "--dest-dir", str(dest2)], check=True, cwd=tmp_path
    )
    science_exe2 = dest2 / science_exe.name
    assert science_exe2.is_file()
    assert science_exe1 != science_exe2
    assert filecmp.cmp(science_exe1, science_exe2, shallow=False), (
        "Expected the new science executable to be able to build itself and produce a "
        "byte-wise identical science executable."
    )


URL = (
    "https://raw.githubusercontent.com/a-scie/lift/1b13720246ab36b21ff20ba256219c3bd79c8a87/LICENSE"
)
EXPECTED_SIZE = 11357
EXPECTED_SHA256_FINGERPRINT = "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"


def url_source_lift_toml_content(
    chroot: Path, expected_size: int, expected_fingerprint: str, lazy: bool
) -> str:
    chroot.mkdir(parents=True, exist_ok=True)
    (chroot / "exe.py").write_text(
        dedent(
            """\
            import sys


            with open(sys.argv[1]) as fp:
                print(fp.readline())
            """
        )
    )

    maybe_type = 'type = "blob"' if lazy else ""
    return dedent(
        f"""\
        [lift]
        name = "url_source"

        [[lift.interpreters]]
        id = "cpython311"
        provider = "PythonBuildStandalone"
        release = "20230116"
        version = "3.11"
        lazy = true

        [[lift.files]]
        name = "exe.py"

        [[lift.files]]
        name = "LICENSE"
        digest = {{ size = {expected_size}, fingerprint = "{expected_fingerprint}" }}
        source = {{ url = "{URL}", lazy = {str(lazy).lower()} }}
        {maybe_type}

        [[lift.commands]]
        exe = "#{{cpython311:python}}"
        args = ["{{exe.py}}", "{{LICENSE}}"]
        """
    )


@dataclass(frozen=True)
class Result:
    scie: Path
    returncode: int
    stdout: str
    stderr: str

    def assert_success(self, assert_url_source_scie_works=True) -> None:
        assert self.returncode == 0, self.stderr
        assert self.scie.is_file()
        if assert_url_source_scie_works:
            assert (
                "Apache License"
                == subprocess.run(
                    args=[str(self.scie)], stdout=subprocess.PIPE, text=True, check=True
                ).stdout.strip()
            )

    def assert_failure(self) -> None:
        assert self.returncode != 0, self.stdout
        assert not self.scie.exists()


def create_url_source_scie(
    tmp_path: Path,
    science_exe: Path,
    lazy: bool = True,
    expected_name: str = "url_source",
    expected_size: int = EXPECTED_SIZE,
    expected_fingerprint: str = EXPECTED_SHA256_FINGERPRINT,
    additional_toml: str = "",
    extra_args: Iterable[str] = (),
    **env: str,
) -> Result:
    dest = tmp_path / "dest"
    chroot = tmp_path / "chroot"
    lift_toml_content = url_source_lift_toml_content(
        chroot,
        lazy=lazy,
        expected_size=expected_size,
        expected_fingerprint=expected_fingerprint,
    )
    lift_toml_content = f"{lift_toml_content}\n{additional_toml}"
    scie = dest / Platform.current().binary_name(expected_name)
    result = subprocess.run(
        args=[str(science_exe), "build", "--dest-dir", str(dest), "-", *extra_args],
        input=lift_toml_content,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=chroot,
        env={**os.environ, **env},
    )
    return Result(
        scie=scie, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr
    )


def test_url_source(tmp_path: Path, science_exe: Path) -> None:
    create_url_source_scie(tmp_path, science_exe, lazy=False).assert_success()


def test_url_source_bad_size(tmp_path: Path, science_exe: Path) -> None:
    bad_size = EXPECTED_SIZE - 1
    result = create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=False,
        expected_size=bad_size,
        SCIENCE_CACHE=str(tmp_path / "cache"),
    )
    result.assert_failure()
    assert re.search(
        rf"The download from {URL} was expected to be {bad_size} bytes, but downloaded "
        rf"{EXPECTED_SIZE} so far.\n",
        result.stderr,
    ), result.stderr


def test_url_source_bad_fingerprint(tmp_path: Path, science_exe: Path) -> None:
    bad_fingerprint = "Slartibartfast"
    result = create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=False,
        expected_fingerprint=bad_fingerprint,
        SCIENCE_CACHE=str(tmp_path / "cache"),
    )
    result.assert_failure()
    assert re.search(
        rf"The download from {URL} has unexpected contents.\n"
        r"Expected sha256 digest:\n"
        rf"\s+{bad_fingerprint}\n"
        r"Actual sha256 digest:\n"
        rf"\s+{EXPECTED_SHA256_FINGERPRINT}\n",
        result.stderr,
    ), result.stderr


def test_url_source_lazy(tmp_path: Path, science_exe: Path) -> None:
    bad_fingerprint = "Slartibartfast"
    result = create_url_source_scie(
        tmp_path, science_exe, lazy=True, expected_fingerprint=bad_fingerprint
    )
    result.assert_success(assert_url_source_scie_works=False)

    scie_base = tmp_path / "nce"
    process = subprocess.run(
        args=[str(result.scie)],
        env={**os.environ, "SCIE_BASE": str(scie_base)},
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.returncode != 0
    destination = scie_base / "Slartibartfast" / "LICENSE"
    assert re.search(
        rf"The blob destination {re.escape(str(destination))} of size {EXPECTED_SIZE} had "
        rf"unexpected hash: {EXPECTED_SHA256_FINGERPRINT}\n",
        process.stderr,
    ), process.stderr


def test_unique_command_names(tmp_path: Path, science_exe: Path) -> None:
    result = create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=True,
        additional_toml=dedent(
            """\
            [[lift.commands]]
            exe = "foo"

            [[lift.commands]]
            name = "bar"
            exe = "baz1"

            [[lift.commands]]
            name = "bar"
            exe = "baz2"

            [[lift.commands]]
            name = "bar"
            exe = "baz3"
            """
        ),
    )
    result.assert_failure()
    assert re.search(
        r"Commands must have unique names. Found the following repeats:\n"
        r"   : 2 instances\n"
        r"bar: 3 instances\n",
        result.stderr,
    ), result.stderr


def test_unique_binding_names(tmp_path: Path, science_exe: Path) -> None:
    result = create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=True,
        additional_toml=dedent(
            """\
            [[lift.bindings]]
            name = "foo"
            exe = "bar"

            [[lift.bindings]]
            name = "foo"
            exe = "bar2"

            [[lift.bindings]]
            name = "baz"
            exe = "spam"
            """
        ),
    )
    result.assert_failure()
    assert re.search(
        r"Binding commands must have unique names. Found the following repeats:\n"
        r"foo: 2 instances\n",
        result.stderr,
    ), result.stderr


def test_reserved_binding_names(tmp_path: Path, science_exe: Path) -> None:
    result = create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=True,
        additional_toml=dedent(
            """\
            [[lift.bindings]]
            name = "fetch"
            exe = "foo"
            """
        ),
    )
    result.assert_failure()
    assert re.search(
        r"Binding commands cannot use the reserved binding names: fetch\n",
        result.stderr,
    ), result.stderr

    # But command names are not reserved.
    create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=True,
        additional_toml=dedent(
            """\
            [[lift.commands]]
            name = "fetch"
            exe = "foo"
            """
        ),
    ).assert_success()


def test_error_handling(tmp_path: Path, science_exe: Path) -> None:
    def expect_error(*, verbose: bool) -> list[str]:
        (tmp_path / "lift.toml").touch()
        args = [str(science_exe)]
        if verbose:
            args.append("-v")
        args.append("build")
        result = subprocess.run(
            args=args, cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        assert result.returncode != 0, result.stdout
        return result.stderr.strip().splitlines(keepends=False)

    expected_error_message = "Expected `[lift]` of type toml table to be defined in lift.toml."

    error_lines = expect_error(verbose=False)
    assert expected_error_message == error_lines[0], os.linesep.join(error_lines)
    if not IS_WINDOWS:
        assert len(error_lines) == 1, (
            "Non-verbose mode should emit just 1 error line, except on Windows where there is a "
            "trailing `Error:...`."
        )

    # N.B.: The complicated scan down for the expected error message line is forced by Windows,
    # which emits an extra `Error:...` as explained above.
    error_lines = expect_error(verbose=True)
    index = -1
    for i, line in enumerate(error_lines):
        if line.endswith(expected_error_message):
            index = i
            break
    assert index > 0, "Expected a backtrace in addition to an error message in verbose mode."

    error_message_line = error_lines[index]
    assert (
        error_message_line != expected_error_message
    ), "Expected an exception type prefix in verbose mode."
    assert error_message_line.endswith(f": {expected_error_message}"), os.linesep.join(error_lines)


def test_include_provenance(tmp_path: Path, science_exe: Path) -> None:
    def create_and_inspect(*args: str, additional_toml: str = "") -> dict[str, Any]:
        result = create_url_source_scie(
            tmp_path, science_exe, additional_toml=additional_toml, extra_args=args
        )
        result.assert_success()
        data = json.loads(
            subprocess.run(
                args=[str(result.scie)],
                env={**os.environ, "SCIE": "inspect"},
                stdout=subprocess.PIPE,
                text=True,
                check=True,
            ).stdout
        )
        assert isinstance(data, dict)
        return data

    assert "science" not in create_and_inspect()

    data = create_and_inspect("--include-provenance")
    build_info = data["science"]
    assert "app_info" not in build_info
    binary_info = build_info["binary"]
    assert __version__ == binary_info["version"]
    assert binary_info["url"].startswith(
        f"https://github.com/a-scie/lift/releases/tag/v{__version__}/"
    )

    data = create_and_inspect(
        "--include-provenance",
        additional_toml=dedent(
            """\
            [lift.app_info]
            foo = "bar"
            baz = 42
            """
        ),
    )
    app_info = data["science"]["app_info"]
    assert "bar" == app_info.pop("foo")
    assert 42 == app_info.pop("baz")
    assert not app_info

    data = create_and_inspect(
        "--include-provenance", "--app-info", "foo=bar", "--app-info", "baz=42"
    )
    app_info = data["science"]["app_info"]
    assert "bar" == app_info.pop("foo")
    assert "42" == app_info.pop("baz")
    assert not app_info

    data = create_and_inspect(
        "--include-provenance",
        "--app-info",
        "foo=bar",
        "--app-info",
        "baz=1/137",
        additional_toml=dedent(
            """\
            [lift.app_info]
            spam = "eggs"
            baz = 42
            """
        ),
    )
    app_info = data["science"]["app_info"]
    assert "eggs" == app_info.pop("spam")
    assert "bar" == app_info.pop("foo")
    assert "1/137" == app_info.pop("baz")
    assert not app_info


def test_invert_lazy(tmp_path: Path, science_exe: Path) -> None:
    result = create_url_source_scie(
        tmp_path, science_exe, lazy=True, extra_args=["--name", "skinny"], expected_name="skinny"
    )
    result.assert_success()
    assert result.scie.name == Platform.current().binary_name("skinny")
    skinny_scie = result.scie

    result = create_url_source_scie(
        tmp_path, science_exe, lazy=False, extra_args=["--name", "fat"], expected_name="fat"
    )
    result.assert_success()
    assert result.scie.name == Platform.current().binary_name("fat")
    fat_scie = result.scie

    assert skinny_scie.stat().st_size < fat_scie.stat().st_size
    assert not filecmp.cmp(skinny_scie, fat_scie, shallow=False)

    result = create_url_source_scie(
        tmp_path / "via-inversion",
        science_exe,
        lazy=True,
        extra_args=["--invert-lazy", "LICENSE", "--name", "fat"],
        expected_name="fat",
    )
    result.assert_success()
    assert fat_scie != result.scie
    assert fat_scie.stat().st_size == result.scie.stat().st_size
    assert filecmp.cmp(fat_scie, result.scie, shallow=False)


def test_invert_lazy_invalid_id(tmp_path: Path, science_exe: Path) -> None:
    result = create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=True,
        extra_args=[
            "--invert-lazy",
            "cpython311",
            "--invert-lazy",
            "foo",
            "--invert-lazy",
            "LICENSE",
            "--invert-lazy",
            "bar",
        ],
    )
    result.assert_failure()
    assert (
        "There following files were not present to invert laziness for: bar, foo"
        == result.stderr.strip()
    )


def test_invert_lazy_non_lazy(tmp_path: Path, science_exe: Path) -> None:
    result = create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=True,
        extra_args=["--invert-lazy", "exe.py"],
    )
    result.assert_failure()
    assert "Cannot lazy fetch local file 'exe.py'." == result.stderr.strip()

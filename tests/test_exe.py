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
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from subprocess import CalledProcessError
from textwrap import dedent
from typing import Any, Iterable

import pytest
import toml
from packaging.version import Version
from pytest import TempPathFactory
from testing import issue

from science import __version__, a_scie
from science.config import parse_config_file
from science.hashing import Digest, Fingerprint
from science.model import ScieJump
from science.os import IS_WINDOWS
from science.platform import CURRENT_PLATFORM, CURRENT_PLATFORM_SPEC, LibC, Os, Platform
from science.providers import PyPy


@pytest.fixture(scope="module")
def config(build_root: Path) -> Path:
    return build_root / "lift.toml"


@pytest.fixture(scope="module")
def docsite(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("docsite")


@pytest.fixture(scope="module")
def science_exe(
    tmp_path_factory: TempPathFactory, build_root: Path, science_pyz: Path, docsite: Path
) -> Path:
    dest = tmp_path_factory.mktemp("dest")
    subprocess.run(
        args=[
            sys.executable,
            str(science_pyz),
            "lift",
            "--file",
            f"science.pyz={science_pyz}",
            "--file",
            f"docsite={docsite}",
            "build",
            "--dest-dir",
            str(dest),
        ],
        check=True,
        cwd=build_root,
    )
    science_exe = dest / CURRENT_PLATFORM.binary_name("science")
    assert science_exe.is_file()
    return science_exe


def test_use_platform_suffix(
    tmp_path: Path, science_exe: Path, config: Path, science_pyz: Path, docsite: Path
) -> None:
    expected_executable = tmp_path / CURRENT_PLATFORM_SPEC.qualified_binary_name("science")
    assert not expected_executable.exists()
    subprocess.run(
        args=[
            str(science_exe),
            "lift",
            "--file",
            f"science.pyz={science_pyz}",
            "--file",
            f"docsite={docsite}",
            "build",
            "--dest-dir",
            str(tmp_path),
            "--use-platform-suffix",
            config,
        ],
        check=True,
    )
    assert expected_executable.is_file()
    assert not (tmp_path / CURRENT_PLATFORM_SPEC.binary_name("science")).exists()


def test_no_use_platform_suffix(
    tmp_path: Path, science_exe: Path, config: Path, science_pyz: Path, docsite: Path
) -> None:
    current_platform = CURRENT_PLATFORM
    foreign_platform = next(plat for plat in Platform if plat is not current_platform)
    expected_executable = tmp_path / foreign_platform.binary_name("science")
    assert not expected_executable.exists()
    subprocess.run(
        args=[
            str(science_exe),
            "lift",
            "--file",
            f"science.pyz={science_pyz}",
            "--file",
            f"docsite={docsite}",
            "--platform",
            foreign_platform.value,
            "build",
            "--dest-dir",
            str(tmp_path),
            "--no-use-platform-suffix",
            config,
        ],
        check=True,
    )
    assert expected_executable.is_file()
    assert not (tmp_path / foreign_platform.qualified_binary_name("science")).exists()


@pytest.fixture(scope="module")
def shasum() -> str | None:
    if not (shasum := which("shasum")):
        return None

    # N.B.: We check to see if shasum actually works since GH Actions Windows 2022 boxes come with a
    # shasum.BAT on the PATH that runs via a perl.exe not on the PATH leading to error.
    try:
        subprocess.run(args=[shasum, "--version"], check=True)
        return shasum
    except (CalledProcessError, OSError):
        return None


def test_hash(
    tmp_path: Path,
    science_exe: Path,
    config: Path,
    science_pyz: Path,
    docsite: Path,
    shasum: str | None,
) -> None:
    expected_executable = tmp_path / CURRENT_PLATFORM.binary_name("science")
    algorithms = "sha1", "sha256", "sha512"
    expected_checksum_paths = [
        Path(f"{expected_executable}.{algorithm}") for algorithm in algorithms
    ]

    for expected_output in expected_executable, *expected_checksum_paths:
        assert not expected_output.exists()

    subprocess.run(
        args=[
            str(science_exe),
            "lift",
            "--file",
            f"science.pyz={science_pyz}",
            "--file",
            f"docsite={docsite}",
            "build",
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
            assert expected_value == actual_digest.hexdigest(), (
                f"The {actual_digest.name} digest did not match."
            )


def test_dogfood(
    tmp_path: Path, science_exe: Path, config: Path, science_pyz: Path, docsite: Path
) -> None:
    dest = tmp_path / "dest"
    subprocess.run(
        args=[
            str(science_exe),
            "lift",
            "--file",
            f"science.pyz={science_pyz}",
            "--file",
            f"docsite={docsite}",
            "build",
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
        science_pyz_file = config_data["lift"]["files"][-1]
        science_pyz_file["key"] = science_pyz_file["name"]
        science_pyz_file["name"] = str(dest.relative_to(tmp_path))
    test_config = tmp_path / "lift.toml"
    with test_config.open("w") as fp:
        toml.dump(config_data, fp)

    application = parse_config_file(test_config)
    parsed_science_pyz_file = application.files[-1]
    assert science_pyz.name == parsed_science_pyz_file.key
    assert str(Path("dist") / science_pyz.name) == parsed_science_pyz_file.name

    (tmp_path / "docsite").mkdir()
    dest1 = tmp_path / "dest1"
    subprocess.run(
        args=[str(science_exe), "lift", "build", "--dest-dir", str(dest1)], check=True, cwd=tmp_path
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
        args=[str(science_exe1), "lift", "build", "--dest-dir", str(dest2)],
        check=True,
        cwd=tmp_path,
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
        release = "20250818"
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


_WORK_DIRS = defaultdict[Path, list[Path]](list[Path])


def create_url_source_scie(
    tmp_path: Path,
    science_exe: Path,
    lazy: bool = True,
    expected_name: str = "url_source",
    expected_size: int = EXPECTED_SIZE,
    expected_fingerprint: str = EXPECTED_SHA256_FINGERPRINT,
    additional_toml: str = "",
    extra_lift_args: Iterable[str] = (),
    **env: str,
) -> Result:
    work_dirs = _WORK_DIRS[tmp_path]
    work_dir = tmp_path / str(len(work_dirs))
    work_dirs.append(work_dir)

    dest = work_dir / "dest"
    chroot = work_dir / "chroot"

    lift_toml_content = url_source_lift_toml_content(
        chroot,
        lazy=lazy,
        expected_size=expected_size,
        expected_fingerprint=expected_fingerprint,
    )
    lift_toml_content = f"{lift_toml_content}\n{additional_toml}"

    scie = dest / CURRENT_PLATFORM.binary_name(expected_name)
    result = subprocess.run(
        args=[str(science_exe), "lift", *extra_lift_args, "build", "--dest-dir", str(dest), "-"],
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
        SCIENCE_CACHE_DIR=str(tmp_path / "cache"),
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
        SCIENCE_CACHE_DIR=str(tmp_path / "cache"),
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
        args.extend(("lift", "build"))
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
    assert error_message_line != expected_error_message, (
        "Expected an exception type prefix in verbose mode."
    )
    assert error_message_line.endswith(f": {expected_error_message}"), os.linesep.join(error_lines)


def test_include_provenance(tmp_path: Path, science_exe: Path) -> None:
    def create_and_inspect(*args: str, additional_toml: str = "") -> dict[str, Any]:
        result = create_url_source_scie(
            tmp_path, science_exe, additional_toml=additional_toml, extra_lift_args=args
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
        f"https://github.com/a-scie/lift/releases/download/v{__version__}/"
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
        tmp_path,
        science_exe,
        lazy=True,
        extra_lift_args=["--app-name", "skinny"],
        expected_name="skinny",
    )
    result.assert_success()
    assert result.scie.name == CURRENT_PLATFORM.binary_name("skinny")
    skinny_scie = result.scie

    result = create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=False,
        extra_lift_args=["--app-name", "fat"],
        expected_name="fat",
    )
    result.assert_success()
    assert result.scie.name == CURRENT_PLATFORM.binary_name("fat")
    fat_scie = result.scie

    assert skinny_scie.stat().st_size < fat_scie.stat().st_size
    assert not filecmp.cmp(skinny_scie, fat_scie, shallow=False)

    result = create_url_source_scie(
        tmp_path / "via-inversion",
        science_exe,
        lazy=True,
        extra_lift_args=["--invert-lazy", "LICENSE", "--app-name", "fat"],
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
        extra_lift_args=[
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
        in result.stderr.strip().splitlines(keepends=False)
    )


def test_invert_lazy_non_lazy(tmp_path: Path, science_exe: Path) -> None:
    result = create_url_source_scie(
        tmp_path,
        science_exe,
        lazy=True,
        extra_lift_args=["--invert-lazy", "exe.py"],
    )
    result.assert_failure()
    assert "Cannot lazy fetch local file 'exe.py'." in result.stderr.strip().splitlines(
        keepends=False
    )


def working_pypy_versions() -> list[str]:
    match CURRENT_PLATFORM:
        case Platform.Linux_s390x:
            return ["2.7", "3.8", "3.9", "3.10"]
        case Platform.Linux_armv7l | Platform.Linux_powerpc64le | Platform.Linux_riscv64:
            return []
        case Platform.Macos_aarch64:
            return ["2.7", "3.8", "3.9", "3.10", "3.11"]
        case Platform.Linux_aarch64:
            return ["2.7", "3.7", "3.8", "3.9", "3.10", "3.11"]
    return ["2.7", "3.6", "3.7", "3.8", "3.9", "3.10", "3.11"]


@pytest.mark.skipif(
    CURRENT_PLATFORM_SPEC not in PyPy.iter_supported_platforms([CURRENT_PLATFORM_SPEC]),
    reason=f"PyPy does not support the current platform: {CURRENT_PLATFORM_SPEC}",
)
@pytest.mark.parametrize("version", working_pypy_versions())
def test_pypy_provider(tmp_path: Path, science_exe: Path, version: str) -> None:
    dest = tmp_path / "dest"
    chroot = tmp_path / "chroot"
    chroot.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        args=[str(science_exe), "lift", "build", "--dest-dir", str(dest), "-"],
        input=dedent(
            f"""\
            [lift]
            name = "pypy"

            [[lift.interpreters]]
            id = "pypy"
            provider = "PyPy"
            version = "{version}"
            lazy = true

            [[lift.commands]]
            exe = "#{{pypy:python}}"
            args = ["-c", "import sys; print('.'.join(map(str, sys.version_info[:2])))"]
            """
        ),
        cwd=chroot,
        text=True,
        check=True,
    )

    scie = dest / CURRENT_PLATFORM.binary_name("pypy")
    assert (
        version
        == subprocess.run(args=[scie], text=True, stdout=subprocess.PIPE, check=True).stdout.strip()
    )


def test_scie_name_collision_with_file(tmp_path: Path, science_exe: Path) -> None:
    dest = tmp_path / "dest"
    chroot = tmp_path / "chroot"
    chroot.mkdir(parents=True, exist_ok=True)

    exe = tmp_path / "exe"
    exe.write_text(
        dedent(
            """\
            import sys


            if __name__ == "__main__":
                print(".".join(map(str, sys.version_info[:3])))
            """
        )
    )

    subprocess.run(
        args=[
            str(science_exe),
            "lift",
            "--file",
            f"exe={exe}",
            "build",
            "--dest-dir",
            str(dest),
            "-",
        ],
        input=dedent(
            """\
            [lift]
            name = "exe"

            [[lift.files]]
            name = "exe"

            [[lift.interpreters]]
            id = "cpython"
            provider = "PythonBuildStandalone"
            release = "20250818"
            version = "3.11"
            lazy = true

            [[lift.commands]]
            exe = "#{cpython:python}"
            args = ["{exe}"]
            """
        ),
        cwd=chroot,
        text=True,
        check=True,
    )

    scie = dest / CURRENT_PLATFORM.binary_name("exe")
    assert os.path.exists(scie)
    assert (
        "3.11.13"
        == subprocess.run(args=[scie], stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    )


def test_pbs_provider_pre_releases(tmp_path: Path, science_exe: Path) -> None:
    dest = tmp_path / "dest"
    chroot = tmp_path / "chroot"
    chroot.mkdir(parents=True, exist_ok=True)

    exe = tmp_path / "exe"
    exe.write_text(
        dedent(
            """\
            import platform


            if __name__ == "__main__":
                print(platform.python_version())
            """
        )
    )

    subprocess.run(
        args=[
            str(science_exe),
            "lift",
            "--file",
            f"exe={exe}",
            "build",
            "--dest-dir",
            str(dest),
            "-",
        ],
        input=dedent(
            """\
            [lift]
            name = "exe"

            [[lift.files]]
            name = "exe"

            [[lift.interpreters]]
            id = "cpython"
            provider = "PythonBuildStandalone"
            release = "20251014"
            version = "3.15"

            [[lift.commands]]
            exe = "#{cpython:python}"
            args = ["{exe}"]
            """
        ),
        cwd=chroot,
        text=True,
        check=True,
    )

    scie = dest / CURRENT_PLATFORM.binary_name("exe")
    assert os.path.exists(scie)
    assert (
        "3.15.0a1"
        == subprocess.run(args=[scie], stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    )


def test_pbs_provider_freethreaded_builds(tmp_path: Path, science_exe: Path) -> None:
    dest = tmp_path / "dest"
    chroot = tmp_path / "chroot"
    chroot.mkdir(parents=True, exist_ok=True)

    exe = tmp_path / "exe"
    exe.write_text(
        dedent(
            """\
            import platform
            import sysconfig


            if __name__ == "__main__":
                print(platform.python_version())
                print(sysconfig.get_config_var("Py_GIL_DISABLED"))
            """
        )
    )

    match Platform.current():
        case Platform.Linux_aarch64 | Platform.Linux_x86_64 if LibC.current() is LibC.GLIBC:
            flavor = "freethreaded+pgo+lto-full"
        case Platform.Macos_aarch64 | Platform.Macos_x86_64:
            flavor = "freethreaded+pgo+lto-full"
        case Platform.Windows_aarch64 | Platform.Windows_x86_64:
            flavor = "freethreaded+pgo-full"
        case platform if platform.os is Os.Linux:
            flavor = "freethreaded+lto-full"
        case _ as unknown_platform:
            assert unknown_platform is None, f"The platform {unknown_platform} is unsupported."

    subprocess.run(
        args=[
            str(science_exe),
            "lift",
            "--file",
            f"exe={exe}",
            "build",
            "--dest-dir",
            str(dest),
            "-",
        ],
        input=dedent(
            f"""\
            [lift]
            name = "exe"

            [[lift.files]]
            name = "exe"

            [[lift.interpreters]]
            id = "python3.14"
            provider = "PythonBuildStandalone"
            release = "20251014"
            version = "3.14"

            [[lift.interpreters]]
            id = "python3.14t"
            provider = "PythonBuildStandalone"
            release = "20251014"
            version = "3.14"
            flavor = "{flavor}"

            [[lift.interpreter_groups]]
            id = "cpython"
            selector = "{{scie.env.PYTHON}}"
            members = [
                "python3.14",
                "python3.14t",
            ]

            [[lift.commands]]
            exe = "#{{cpython:python}}"
            args = ["{{exe}}"]
            """
        ),
        cwd=chroot,
        text=True,
        check=True,
    )

    scie = dest / CURRENT_PLATFORM.binary_name("exe")
    assert os.path.exists(scie)

    assert ["3.14.0", "0"] == subprocess.run(
        args=[scie],
        env={**os.environ, "PYTHON": "python3.14"},
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.splitlines()

    assert ["3.14.0", "1"] == subprocess.run(
        args=[scie],
        env={**os.environ, "PYTHON": "python3.14t"},
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.splitlines()


def test_pbs_provider_version_suffix(tmp_path: Path, science_exe: Path) -> None:
    dest = tmp_path / "dest"
    chroot = tmp_path / "chroot"
    chroot.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        args=[str(science_exe), "lift", "build", "--dest-dir", str(dest), "-"],
        input=dedent(
            """\
            [lift]
            name = "exe"

            [[lift.interpreters]]
            id = "cpython"
            provider = "PythonBuildStandalone"
            release = "20251014"
            version = "3.14.0t"
            flavor = "install_only"

            [[lift.commands]]
            exe = "#{cpython:python}"
            args = ["-VV"]
            """
        ),
        cwd=chroot,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode != 0
    expected_error_message_lines = [
        "Failed to parse `[lift.interpreters[1]] provider`.",
        "",
        "Tried:",
        (
            "Provider: The suffix 't' of version '3.14.0t' indicates a freethreaded flavor "
            "CPython build should be selected and cannot be combined with the explicit flavor "
            "'install_only'."
        ),
        "Either use a version suffix or an explicit flavor, but not both.",
    ]
    assert (
        expected_error_message_lines
        == result.stderr.strip().splitlines()[: len(expected_error_message_lines)]
    ), result.stderr

    exe = tmp_path / "exe"
    exe.write_text(
        dedent(
            """\
            import json
            import platform
            import sys
            import sysconfig


            if __name__ == "__main__":
                json.dump(
                    {
                        "python_version": platform.python_version(),
                        "debug": sysconfig.get_config_var("Py_DEBUG"),
                        "free-threaded": sysconfig.get_config_var("Py_GIL_DISABLED"),
                    },
                    sys.stdout,
                )
            """
        )
    )

    manifest = dedent(
        """\
        [lift]
        name = "exe"

        [[lift.files]]
        name = "exe"

        [[lift.interpreters]]
        id = "python3.14"
        provider = "PythonBuildStandalone"
        release = "20251014"
        version = "3.14"

        [[lift.interpreters]]
        id = "python3.14t"
        provider = "PythonBuildStandalone"
        release = "20251014"
        version = "3.14t"

        [[lift.commands]]
        exe = "#{cpython:python}"
        args = ["{exe}"]
        """
    )

    # N.B.: PBS does not have debug builds for Windows.
    if Os.current() == Os.Windows:
        manifest = dedent(
            """\
            {manifest}

            [[lift.interpreter_groups]]
            id = "cpython"
            selector = "{{scie.env.PYTHON}}"
            members = [
                "python3.14",
                "python3.14t",
            ]
            """
        ).format(manifest=manifest)
    else:
        manifest = dedent(
            """\
            {manifest}

            [[lift.interpreters]]
            id = "python3.14d"
            provider = "PythonBuildStandalone"
            release = "20251014"
            version = "3.14d"

            [[lift.interpreters]]
            id = "python3.14td"
            provider = "PythonBuildStandalone"
            release = "20251014"
            version = "3.14td"

            [[lift.interpreter_groups]]
            id = "cpython"
            selector = "{{scie.env.PYTHON}}"
            members = [
                "python3.14",
                "python3.14t",
                "python3.14td",
                "python3.14d",
            ]
            """
        ).format(manifest=manifest)

    subprocess.run(
        args=[
            str(science_exe),
            "lift",
            "--file",
            f"exe={exe}",
            "build",
            "--dest-dir",
            str(dest),
            "-",
        ],
        input=manifest,
        cwd=chroot,
        text=True,
        check=True,
    )

    scie = dest / CURRENT_PLATFORM.binary_name("exe")
    assert os.path.exists(scie)

    def scie_select(python) -> dict[str, Any]:
        return json.loads(
            subprocess.run(
                args=[scie],
                env={**os.environ, "PYTHON": python},
                stdout=subprocess.PIPE,
                text=True,
                check=True,
            ).stdout
        )

    assert {
        "python_version": "3.14.0",
        "debug": 0,
        "free-threaded": 0,
    } == scie_select("python3.14")

    assert {
        "python_version": "3.14.0",
        "debug": 0,
        "free-threaded": 1,
    } == scie_select("python3.14t")

    # N.B.: PBS does not have debug builds for Windows.
    if Os.current() is not Os.Windows:
        assert {
            "python_version": "3.14.0",
            "debug": 1,
            "free-threaded": 1,
        } == scie_select("python3.14td")

        assert {
            "python_version": "3.14.0",
            "debug": 1,
            "free-threaded": 0,
        } == scie_select("python3.14d")


def test_load_dotenv(tmp_path: Path, science_exe: Path) -> None:
    dest = tmp_path / "dest"
    chroot = tmp_path / "chroot"
    chroot.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        args=[str(science_exe), "lift", "build", "--dest-dir", str(dest), "-"],
        input=dedent(
            """\
            [lift]
            name = "exe"
            load_dotenv = true

            [[lift.interpreters]]
            id = "cpython"
            provider = "PythonBuildStandalone"
            release = "20251120"
            version = "3.14"
            flavor = "install_only_stripped"

            [[lift.commands]]
            exe = "#{cpython:python}"
            args = ["-c", "import os; print(os.environ.get('SLARTIBARTFAST', '<unset>'))"]
            """
        ),
        cwd=chroot,
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    exe = dest / "exe"
    assert (
        "<unset>"
        == subprocess.run(args=[exe], stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    )
    (dest / ".env").write_text("SLARTIBARTFAST=42")
    assert (
        "<unset>"
        == subprocess.run(args=[exe], stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    )
    assert (
        "42"
        == subprocess.run(
            args=[exe], stdout=subprocess.PIPE, text=True, check=True, cwd=dest
        ).stdout.strip()
    )


@pytest.mark.parametrize("version", ["1.8.0", "1.8.1", "1.8.2"])
def test_custom_jump_nominal(tmp_path: Path, science_exe: Path, version: str) -> None:
    dest = tmp_path / "dest"
    chroot = tmp_path / "chroot"
    chroot.mkdir(parents=True, exist_ok=True)

    lift_manifest = chroot / "lift.toml"
    lift_manifest.write_text(
        dedent(
            f"""\
            [lift]
            name = "exe"

            [lift.scie_jump]
            version = "{version}"

            [[lift.interpreters]]
            id = "cpython"
            provider = "PythonBuildStandalone"
            release = "20251120"
            version = "3.14"
            flavor = "install_only_stripped"

            [[lift.commands]]
            exe = "#{{cpython:python}}"
            args = ["-V"]
            """
        )
    )

    cache_dir = tmp_path / "cache"
    subprocess.run(
        args=[str(science_exe), "lift", "build", "--dest-dir", str(dest), lift_manifest],
        env={**os.environ, "SCIENCE_CACHE_DIR": str(cache_dir)},
        check=True,
    )
    exe = dest / Platform.current().binary_name("exe")

    split_dir = tmp_path / "split"
    subprocess.run(args=[exe, split_dir], env={**os.environ, "SCIE": "split"}, check=True)
    assert (
        version
        == subprocess.run(
            args=[split_dir / "scie-jump", "-V"], stdout=subprocess.PIPE, text=True, check=True
        ).stdout.strip()
    )

    result = subprocess.run(
        args=[exe],
        env={**os.environ, "SCIE": "inspect"},
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    manifest = json.loads(result.stdout)
    assert version == manifest["scie"]["jump"]["version"]

    load_result = a_scie.jump(ScieJump(version=Version(version)))
    assert load_result.digest.size == manifest["scie"]["jump"]["size"]
    assert os.path.getsize(load_result.path) == manifest["scie"]["jump"]["size"]


VERSION = "1.8.2"
GOOD_SIZE = 2223910
GOOD_FINGERPRINT = Fingerprint("e7ebc56578041eb5c92d819f948f9c8d5a671afaa337720d7d310f5311a2c5c3")

BAD_SIZE = -1
BAD_FINGERPRINT = Fingerprint("bad")


def digest_id(size: int | None, fingerprint: str | None) -> str:
    if size and fingerprint:
        components = ["digest"]
        if size == BAD_SIZE:
            components.append("bad-size")
        if fingerprint == BAD_FINGERPRINT:
            components.append("bad-fingerprint")
        return "-".join(components)
    if size:
        return "bad-size" if size == BAD_SIZE else "size"
    if fingerprint:
        return "bad-fingerprint" if fingerprint == BAD_FINGERPRINT else "fingerprint"
    return "no-digest"


def as_toml_line(digest: Digest) -> str:
    digest_fields = []
    if digest.size:
        digest_fields.append(f"size = {digest.size}")
    if digest.fingerprint:
        digest_fields.append(f'fingerprint = "{digest.fingerprint}"')
    if not digest_fields:
        return ""
    return f"digest = {{ {', '.join(digest_fields)} }}"


@pytest.mark.parametrize(
    "digest",
    [
        pytest.param(Digest(size=size, fingerprint=fingerprint), id=digest_id(size, fingerprint))
        for size, fingerprint in itertools.product(
            (GOOD_SIZE, BAD_SIZE, None), (GOOD_FINGERPRINT, BAD_FINGERPRINT, None)
        )
    ],
)
def test_custom_jump_invalid(tmp_path: Path, science_exe: Path, digest: Digest) -> None:
    dest = tmp_path / "dest"
    chroot = tmp_path / "chroot"
    chroot.mkdir(parents=True, exist_ok=True)

    lift_manifest = chroot / "lift.toml"
    lift_manifest.write_text(
        dedent(
            """\
            [lift]
            name = "inspect"
            platforms = [{{ platform = "linux-x86_64", libc = "gnu" }}]

            [lift.scie_jump]
            version = "{version}"
            {digest}

            [[lift.commands]]
            exe = "{{scie}}"
            [lift.commands.env.replace]
            SCIE = "inspect"
            """
        ).format(version=VERSION, digest=as_toml_line(digest))
    )

    cache_dir = tmp_path / "cache"
    result = subprocess.run(
        args=[str(science_exe), "lift", "build", "--dest-dir", str(dest)],
        env={**os.environ, "SCIENCE_CACHE_DIR": str(cache_dir)},
        cwd=chroot,
        stderr=subprocess.PIPE,
        text=True,
    )
    if digest.size == BAD_SIZE:
        assert result.returncode != 0
        assert (
            "The content at "
            f"https://github.com/a-scie/jump/releases/download/v{VERSION}/scie-jump-linux-x86_64 "
            f"is expected to be {BAD_SIZE} bytes, but advertises a Content-Length of {GOOD_SIZE} "
            "bytes."
        ) in result.stderr
    elif digest.fingerprint == BAD_FINGERPRINT:
        assert result.returncode != 0
        assert (
            "The download from "
            f"https://github.com/a-scie/jump/releases/download/v{VERSION}/scie-jump-linux-x86_64 "
            f"has unexpected contents.\n"
            "Expected sha256 digest:\n"
            f"  {BAD_FINGERPRINT}\n"
            "Actual sha256 digest:\n"
            f"  {GOOD_FINGERPRINT}"
        ) in result.stderr
    else:
        assert 0 == result.returncode
        manifest = json.loads(
            subprocess.run(
                args=[dest / Platform.current().binary_name("inspect")],
                stdout=subprocess.PIPE,
                check=True,
            ).stdout
        )
        assert VERSION == manifest["scie"]["jump"]["version"]
        assert (digest.size or GOOD_SIZE) == manifest["scie"]["jump"]["size"]

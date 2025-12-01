# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from textwrap import dedent
from threading import Thread
from typing import Iterator

import pytest
from pytest import MonkeyPatch

from science import a_scie
from science.hashing import Digest
from science.platform import CURRENT_PLATFORM_SPEC, Platform, PlatformSpec
from science.providers import PyPy


@pytest.fixture(autouse=True)
def cache_dir(monkeypatch: MonkeyPatch, tmp_path: Path) -> Path:
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("SCIENCE_CACHE", str(cache_dir))
    return cache_dir


@dataclass(frozen=True)
class Server:
    port: int
    root: Path

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@pytest.fixture
def server(tmp_path: Path) -> Iterator[Server]:
    serve_root = tmp_path / "http-root"
    serve_root.mkdir()

    # N.B.: Running Python in unbuffered mode here is critical to being able to read stdout.
    process = subprocess.Popen(
        args=[sys.executable, "-u", "-m", "http.server", "0"],
        cwd=serve_root,
        stdout=subprocess.PIPE,
    )
    try:
        port: Queue[int] = Queue()

        def read_data():
            try:
                data = process.stdout.readline()
                match = re.match(rb"^Serving HTTP on \S+ port (?P<port>\d+)\D", data)
                port.put(int(match.group("port")))
            finally:
                port.task_done()

        reader = Thread(target=read_data)
        reader.daemon = True
        reader.start()
        port.join()
        reader.join()

        yield Server(port=port.get(), root=serve_root)
    finally:
        process.kill()


def assert_download_mirror(
    tmp_path: Path, current_platform_spec: PlatformSpec, *, download_dir: Path, download_url: str
) -> None:
    subprocess.run(args=["science", "download", "ptex", download_dir], check=True)
    subprocess.run(args=["science", "download", "scie-jump", download_dir], check=True)

    lift_manifest = tmp_path / "lift.toml"
    scie_jump_qualified_binary_name = a_scie.qualify_binary_name(
        "scie-jump", platform_spec=current_platform_spec
    )
    lift_manifest.write_text(
        dedent(
            f"""\
            [lift]
            name = "mirror"
            description = "Test mirroring."

            [lift.ptex]
            base_url = "{download_url}/ptex/"

            [lift.scie_jump]
            base_url = "{download_url}/jump"

            [[lift.commands]]
            exe = "{{ptex}}"
            args = ["-O", "{download_url}/jump/latest/download/{scie_jump_qualified_binary_name}"]
            """
        )
    )
    subprocess.run(args=["science", "lift", "build", lift_manifest], cwd=tmp_path, check=True)

    scie = tmp_path / current_platform_spec.binary_name("mirror")
    split_dir = tmp_path / "split"
    subprocess.run(args=[scie, split_dir], env={**os.environ, "SCIE": "split"}, check=True)
    subprocess.run(args=[scie], cwd=tmp_path, check=True)

    assert Digest.hash(tmp_path / scie_jump_qualified_binary_name) == Digest.hash(
        split_dir / current_platform_spec.binary_name("scie-jump")
    )


def test_download_http_mirror(
    tmp_path: Path, current_platform_spec: PlatformSpec, server: Server
) -> None:
    assert_download_mirror(
        tmp_path, current_platform_spec, download_dir=server.root, download_url=server.url
    )


def test_download_file_mirror(tmp_path: Path, current_platform_spec: PlatformSpec) -> None:
    download_dir = tmp_path / "download-dir"
    download_dir_url = (
        f"file:///{download_dir.as_posix()}"
        if current_platform_spec.is_windows
        else f"file://{download_dir}"
    )
    assert_download_mirror(
        tmp_path, current_platform_spec, download_dir=download_dir, download_url=download_dir_url
    )


def test_pbs_mirror(tmp_path: Path, current_platform: Platform) -> None:
    download_dir = tmp_path / "download-dir"
    subprocess.run(
        args=[
            "science",
            "download",
            "provider",
            "PythonBuildStandalone",
            "--version",
            "3.13",
            "--release",
            "20251120",
            "--flavor",
            "install_only_stripped",
            download_dir,
        ],
        check=True,
    )

    download_dir_url = (
        f"file:///{download_dir.as_posix()}"
        if current_platform.is_windows
        else f"file://{download_dir}"
    )
    lift_manifest = tmp_path / "lift.toml"
    lift_manifest.write_text(
        dedent(
            f"""\
            [lift]
            name = "mirror"
            description = "Test mirroring."

            [[lift.interpreters]]
            id = "cpython"
            provider = "PythonBuildStandalone"
            release = "20251120"
            version = "3.13"
            flavor = "install_only_stripped"
            base_url = "{download_dir_url}/providers/PythonBuildStandalone"

            [[lift.commands]]
            exe = "#{{cpython:python}}"
            args = ["-V"]
            """
        )
    )
    subprocess.run(args=["science", "lift", "build", lift_manifest], cwd=tmp_path, check=True)

    assert (
        "Python 3.13.9"
        == subprocess.run(
            args=[tmp_path / current_platform.binary_name("mirror")],
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout.strip()
    )


@pytest.mark.skipif(
    CURRENT_PLATFORM_SPEC not in frozenset(PyPy.iter_supported_platforms([CURRENT_PLATFORM_SPEC])),
    reason="PyPy does not have pre-built distributions for the current platform.",
)
def test_pypy_mirror(tmp_path: Path, current_platform: Platform) -> None:
    download_dir = tmp_path / "download-dir"
    subprocess.run(
        args=[
            "science",
            "download",
            "provider",
            "PyPy",
            "--version",
            "3.9",
            "--release",
            "v7.3.15",
            download_dir,
        ],
        check=True,
    )

    download_dir_url = (
        f"file:///{download_dir.as_posix()}"
        if current_platform.is_windows
        else f"file://{download_dir}"
    )
    lift_manifest = tmp_path / "lift.toml"
    lift_manifest.write_text(
        dedent(
            f"""\
            [lift]
            name = "mirror"
            description = "Test mirroring."

            [[lift.interpreters]]
            id = "cpython"
            provider = "PyPy"
            release = "v7.3.15"
            version = "3.9"
            base_url = "{download_dir_url}/providers/PyPy"

            [[lift.commands]]
            exe = "#{{cpython:python}}"
            args = ["-V"]
            """
        )
    )
    subprocess.run(args=["science", "lift", "build", lift_manifest], cwd=tmp_path, check=True)

    assert (
        subprocess.run(
            args=[tmp_path / current_platform.binary_name("mirror")],
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        .stdout.strip()
        .startswith("Python 3.9.18 (9c4f8ef178b6, Jan 14 2024, ")
    )

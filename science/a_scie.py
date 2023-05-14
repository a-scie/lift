# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import atexit
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from packaging.version import Version

from science.fetcher import fetch_and_verify
from science.hashing import Fingerprint
from science.model import Digest, File, Ptex, ScieJump, Url
from science.platform import Platform


@dataclass(frozen=True)
class _LoadResult:
    path: Path
    binary_name: str


def _load_project_release(
    project_name: str,
    binary_name: str,
    version: Version | None = None,
    fingerprint: Digest | Fingerprint | None = None,
    platform: Platform = Platform.current(),
) -> _LoadResult:
    qualified_binary_name = platform.qualified_binary_name(binary_name)
    base_url = f"https://github.com/a-scie/{project_name}/releases"
    if version:
        version_path = f"download/v{version}"
        ttl = None
    else:
        version_path = "latest/download"
        ttl = timedelta(days=5)
    path = fetch_and_verify(
        url=Url(f"{base_url}/{version_path}/{qualified_binary_name}"),
        fingerprint=fingerprint,
        executable=True,
        ttl=ttl,
    )
    return _LoadResult(path=path, binary_name=qualified_binary_name)


def jump(specification: ScieJump | None = None, platform: Platform = Platform.current()) -> Path:
    version = specification.version if specification else None
    fingerprint = specification.digest if specification and specification.digest else None
    return _load_project_release(
        project_name="jump",
        binary_name="scie-jump",
        version=version,
        fingerprint=fingerprint,
        platform=platform,
    ).path


def custom_jump(repo_path: Path) -> Path:
    dist_dir = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, dist_dir, ignore_errors=True)
    subprocess.run(
        args=["cargo", "run", "-p", "package", "--", dist_dir], cwd=repo_path, check=True
    )
    return Path(dist_dir) / Platform.current().qualified_binary_name("scie-jump")


def ptex(
    dest_dir: Path, specification: Ptex | None = None, platform: Platform = Platform.current()
) -> File:
    version = specification.version if specification else None
    fingerprint = specification.digest if specification and specification.digest else None
    result = _load_project_release(
        project_name="ptex",
        fingerprint=fingerprint,
        binary_name="ptex",
        version=version,
        platform=platform,
    )
    (dest_dir / result.binary_name).symlink_to(result.path)
    ptex_key = specification.id.value if specification and specification.id else "ptex"
    return File(name=result.binary_name, key=ptex_key, is_executable=True)

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

from science.fetcher import FetchResult, fetch_and_verify
from science.hashing import Digest, Fingerprint
from science.model import Ptex, ScieJump, Url
from science.platform import CURRENT_PLATFORM, CURRENT_PLATFORM_SPEC, Platform, PlatformSpec


def qualify_binary_name(
    binary_name: str,
    version: Version | None = None,
    platform_spec: PlatformSpec = CURRENT_PLATFORM_SPEC,
) -> str:
    # N.B.: The scie-jump added support for `-{gnu,musl}-linux-{aarch,x86_}64` suffixes in the
    # 1.9.0 release.
    if (
        platform_spec.libc
        and binary_name == "scie-jump"
        and platform_spec.platform in (Platform.Linux_aarch64, Platform.Linux_x86_64)
        and (not version or version >= Version("1.9.0"))
    ):
        return platform_spec.qualified_binary_name(binary_name, gnu_prefix=True)

    return platform_spec.platform.qualified_binary_name(binary_name)


@dataclass(frozen=True)
class LoadResult(FetchResult):
    binary_name: str
    version: Version | None = None


def load_project_release(
    project_name: str,
    binary_name: str,
    version: Version | None = None,
    fingerprint: Digest | Fingerprint | None = None,
    platform_spec: PlatformSpec = CURRENT_PLATFORM_SPEC,
    base_url: Url | None = None,
) -> LoadResult:
    qualified_binary_name = qualify_binary_name(
        binary_name, version=version, platform_spec=platform_spec
    )
    root_url = (base_url or f"https://github.com/a-scie/{project_name}/releases").rstrip("/")
    if version:
        version_path = f"download/v{version}"
        ttl = None
    else:
        version_path = "latest/download"
        ttl = timedelta(days=5)
    result = fetch_and_verify(
        url=Url(f"{root_url}/{version_path}/{qualified_binary_name}"),
        fingerprint=fingerprint,
        executable=True,
        ttl=ttl,
    )
    return LoadResult(
        path=result.path, digest=result.digest, binary_name=qualified_binary_name, version=version
    )


def jump(
    specification: ScieJump | None = None, platform_spec: PlatformSpec = CURRENT_PLATFORM_SPEC
) -> LoadResult:
    version = specification.version if specification else None
    fingerprint = specification.digest if specification and specification.digest else None
    base_url = specification.base_url if specification else None
    return load_project_release(
        project_name="jump",
        binary_name="scie-jump",
        version=version,
        fingerprint=fingerprint,
        platform_spec=platform_spec,
        base_url=base_url,
    )


def custom_jump(repo_path: Path) -> LoadResult:
    dist_dir = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, dist_dir, ignore_errors=True)
    subprocess.run(
        args=["cargo", "run", "-p", "package", "--", dist_dir], cwd=repo_path, check=True
    )
    qualified_binary_name = CURRENT_PLATFORM.qualified_binary_name("scie-jump")
    path = Path(dist_dir) / qualified_binary_name
    return LoadResult(path=path, digest=Digest.hash(path), binary_name=qualified_binary_name)


def ptex(
    specification: Ptex | None = None, platform_spec: PlatformSpec = CURRENT_PLATFORM_SPEC
) -> LoadResult:
    version = specification.version if specification else None
    fingerprint = specification.digest if specification and specification.digest else None
    base_url = specification.base_url if specification else None
    return load_project_release(
        project_name="ptex",
        binary_name="ptex",
        version=version,
        fingerprint=fingerprint,
        platform_spec=platform_spec,
        base_url=base_url,
    )

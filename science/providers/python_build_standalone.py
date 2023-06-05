# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import os
import re
from dataclasses import dataclass
from datetime import timedelta

from packaging.version import Version

from science.cache import download_cache
from science.dataclass.reflect import metadata
from science.errors import InputError
from science.fetcher import fetch_json, fetch_text
from science.frozendict import FrozenDict
from science.hashing import Digest, Fingerprint
from science.model import Distribution, Fetch, File, FileType, Identifier, Provider, Url
from science.platform import Platform


@dataclass(frozen=True)
class FingerprintedAsset:
    url: Url
    name: str
    digest: Digest
    version: Version
    target_triple: str
    file_type: FileType


@dataclass(frozen=True)
class Asset:
    url: Url
    name: str
    size: int
    version: str
    target_triple: str
    extension: str

    def with_fingerprint(self, fingerprint: Fingerprint) -> FingerprintedAsset:
        return FingerprintedAsset(
            url=self.url,
            name=self.name,
            digest=Digest(size=self.size, fingerprint=fingerprint),
            version=Version(self.version),
            target_triple=self.target_triple,
            file_type=FileType.for_extension(self.extension),
        )


@dataclass(frozen=True)
class Config:
    version: str = dataclasses.field(
        metadata=metadata(
            """The CPython version to select.

            Can be either in `<major>.<minor>` form; e.g.: '3.11', or else fully specified as
            `<major>.<minor>.<patch>`; e.g.: '3.11.3'.

            ```{caution}
            Python Standalone Builds does not provide all patch versions; so you should check
            [their releases](https://github.com/indygreg/python-build-standalone/releases) if you
            wish to pin down to the patch level.
            ```
            """
        )
    )
    release: str | None = dataclasses.field(
        default=None,
        metadata=metadata(
            f"""Python Standalone Builds release to use.

            Currently releases are dates of the form `YYYYMMDD`, e.g.: '20230507'.
            See the [GitHub releases page][releases-page] to discover available releases.

            If left unspecified the latest release is used.

            ```{{note}}
            The latest lookup is cached for 5 days. To force a fresh lookup you can remove
            the cache at `{download_cache().base_dir}`.
            ```

            [releases-page]: https://github.com/indygreg/python-build-standalone/releases
            """
        ),
    )
    flavor: str = dataclasses.field(
        default="install_only",
        metadata=metadata(
            """The flavor of the Python Standalone Builds release to use.

            Currently only accepts 'install_only' which is the default.
            """
        ),
    )


@dataclass(frozen=True)
class PythonBuildStandalone(Provider[Config]):
    """Provides distributions from the [Python Standalone Builds][PBS] project.

    All science platforms are supported for Python 3 minor versions >= 8.

    For all platforms, a `python` placeholder (`#{<id>:python}`) is supported and will be
    substituted with the selected distribution's Python binary path.

    On the Linux and MacOS platforms a `pip` placeholder (`#{<id>:pip}`) is supported and will be
    substituted with the selected distribution's pip script path.

    ```{danger}
    Mutating the
    distribution with `pip install` or `pip uninstall` is almost always a bad idea. The Python
    Standalone Builds distributions are unpacked in the shared scie file cache atomically, but any
    mutations after the initial unpacking are not guarded; as such, you risk concurrency bugs not to
    mention all the problems associated with mutating a shared Python distribution's site-packages:
    namely, you can silently break other users of the shared Python distribution. If you have a need
    to use `pip install`, you probably want to use the `--prefix` or `--target` options or else
    instead create a venv using the venv module (`-m venv`) and then mutate that private venv using
    its `pip` script.
    ```

    [PBS]: https://python-build-standalone.readthedocs.io
    """

    @staticmethod
    def rank_compatibility(platform: Platform, target_triple: str) -> int | None:
        match platform:
            case Platform.Linux_aarch64:
                match target_triple:
                    case "aarch64-unknown-linux-gnu":
                        return 0
            case Platform.Linux_x86_64:
                match target_triple:
                    case "x86_64-unknown-linux-gnu":
                        return 0
                    case "x86_64_v2-unknown-linux-gnu":
                        return 1
                    case "x86_64_v3-unknown-linux-gnu":
                        return 2
                    case "x86_64-unknown-linux-musl":
                        return 3
                    case "x86_64_v4-unknown-linux-gnu":
                        return 4
            case Platform.Macos_aarch64:
                match target_triple:
                    case "aarch64-apple-darwin":
                        return 0
            case Platform.Macos_x86_64:
                match target_triple:
                    case "x86_64-apple-darwin":
                        return 0
            case Platform.Windows_x86_64:
                match target_triple:
                    case "x86_64-pc-windows-msvc-shared":
                        return 0
                    case "x86_64-pc-windows-msvc-static":
                        return 1
        return None

    @classmethod
    def config_dataclass(cls) -> type[Config]:
        return Config

    @classmethod
    def create(cls, identifier: Identifier, lazy: bool, config: Config) -> PythonBuildStandalone:
        api_url = "https://api.github.com/repos/indygreg/python-build-standalone/releases"
        if config.release:
            release_url = Url(f"{api_url}/tags/{config.release}")
            ttl = None
        else:
            release_url = Url(f"{api_url}/latest")
            ttl = timedelta(days=5)
        release_data = fetch_json(release_url, ttl=ttl)

        release = release_data["name"]
        version = Version(config.version)
        # Names are like:
        #  cpython-3.9.16+20221220-x86_64_v3-unknown-linux-musl-install_only.tar.gz
        name_re = re.compile(
            rf"^cpython-(?P<exact_version>{re.escape(str(version))}(?:\.\d+)*)"
            rf"\+{re.escape(release)}-(?P<target_triple>.+)-{re.escape(config.flavor)}"
            r"\.(?P<extension>.+)$"
        )

        # N.B.: There are 3 types of files in PythonBuildStandalone releases:
        # 1. The release archive.
        # 2. The release archive .sah256 file with its individual checksum.
        # 3. The SHA256SUMS file with all the release archive checksums.
        sha256sums_url: Url | None = None
        asset_mapping = {}
        for asset in release_data["assets"]:
            name = asset["name"]
            if "SHA256SUMS" == name:
                sha256sums_url = Url(asset["browser_download_url"])
            elif name.endswith(".sha256"):
                continue
            elif match := name_re.match(name):
                url = asset["browser_download_url"]
                size = asset["size"]
                exact_version = match["exact_version"]
                target_triple = match["target_triple"]
                extension = match["extension"]
                asset_mapping[name] = Asset(
                    url=Url(url),
                    name=name,
                    size=size,
                    version=exact_version,
                    target_triple=target_triple,
                    extension=extension,
                )

        if not sha256sums_url:
            raise InputError(f"Did not find expected SHA256SUMS asset for release {release}.")

        sha256sums = {}
        for line_no, line in enumerate(fetch_text(sha256sums_url).splitlines(), start=1):
            if line := line.strip():
                parts = re.split(r"\s+", line)
                if len(parts) != 2:
                    raise InputError(
                        f"Line {line_no} from {sha256sums_url} has unexpected content:\n{line}"
                    )
                fingerprint, name = parts
                sha256sums[name] = Fingerprint(fingerprint)

        fingerprinted_assets = []
        for name, asset in asset_mapping.items():
            fingerprint = sha256sums[name]
            fingerprinted_assets.append(asset.with_fingerprint(fingerprint))

        if not fingerprinted_assets:
            raise InputError(
                f"No released assets found for release {release} Python {version} of flavor "
                f"{config.flavor}."
            )

        return cls(
            id=identifier,
            lazy=lazy,
            release=release,
            version=version,
            flavor=config.flavor,
            assets=tuple(fingerprinted_assets),
        )

    id: Identifier
    lazy: bool
    release: str
    version: Version
    flavor: str
    assets: tuple[FingerprintedAsset, ...]

    def distribution(self, platform: Platform) -> Distribution | None:
        selected_asset: FingerprintedAsset | None = None
        asset_rank: int | None = None
        for asset in self.assets:
            if (rank := self.rank_compatibility(platform, asset.target_triple)) is not None and (
                asset_rank is None or rank < asset_rank
            ):
                asset_rank = rank
                selected_asset = asset
        if selected_asset is None:
            raise InputError(
                f"No compatible distribution was found for {platform} from amongst:\n"
                f"{os.linesep.join(asset.name for asset in self.assets)}"
            )

        file = File(
            name=selected_asset.name,
            key=self.id,
            digest=selected_asset.digest,
            type=selected_asset.file_type,
            is_executable=False,
            eager_extract=False,
            source=Fetch(url=Url(selected_asset.url), lazy=self.lazy),
        )
        placeholders = {}
        match self.flavor:
            case "install_only":
                match platform:
                    case Platform.Windows_x86_64:
                        placeholders[Identifier("python")] = "python\\python.exe"
                    case _:
                        version = f"{selected_asset.version.major}.{selected_asset.version.minor}"
                        placeholders[Identifier("python")] = f"python/bin/python{version}"
                        placeholders[Identifier("pip")] = f"python/bin/pip{version}"
            case flavor:
                raise InputError(
                    "PythonBuildStandalone currently only understands the 'install_only' flavor of "
                    f"distribution, given: {flavor}"
                )
        return Distribution(id=self.id, file=file, placeholders=FrozenDict(placeholders))

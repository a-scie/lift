# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import os
import re
from dataclasses import dataclass
from datetime import timedelta

from bs4 import BeautifulSoup
from packaging.version import Version

from science.cache import download_cache
from science.dataclass.reflect import metadata
from science.errors import InputError
from science.fetcher import configured_client, fetch_text
from science.frozendict import FrozenDict
from science.hashing import Digest, Fingerprint
from science.model import Distribution, Fetch, File, FileType, Identifier, Provider, Url
from science.platform import Platform


@dataclass(frozen=True)
class FingerprintedAsset:
    url: Url
    name: str
    extension: str
    version: Version
    release: str
    arch: str
    fingerprint: Fingerprint
    file_type: FileType

    def file_stem(self) -> str:
        return self.name[: -(len(self.extension) + 1)]


@dataclass(frozen=True)
class Config:
    version: str = dataclasses.field(
        metadata=metadata(
            """The Python version to select.

            Must be in `<major>.<minor>` form; e.g.: '3.11'.

            ```{caution}
            PyPy does not provide all minor versions; so you should check
            [their releases page][releases-page] to make sure they support the version you want.
            ```

            [releases-page]: https://downloads.python.org/pypy/
            """
        )
    )
    release: str | None = dataclasses.field(
        default=None,
        metadata=metadata(
            f"""The PyPy release to use.

            Currently, stable releases are of the form `v<major>.<minor>.<patch>`, e.g.: 'v7.3.16'.
            See the [PyPy releases page][releases-page] to discover available releases.

            If left unspecified the [latest release][latest-release] providing the specified Python
            version is used.

            ```{{note}}
            The latest lookup is cached for 5 days. To force a fresh lookup you can remove
            the cache at `{download_cache().base_dir}`.
            ```

            [releases-page]: https://downloads.python.org/pypy/
            [latest-release]: https://pypy.org/download.html
            """
        ),
    )


@dataclass(frozen=True)
class PyPy(Provider[Config]):
    """Provides distributions from the [PyPy][PyPy] project.

    All science platforms are supported for PyPy release v7.3.0 and up.

    ```{note}
    Windows ARM64 uses the x86-64 binaries since there are currently no Windows ARM64 releases
    from [PyPy][PyPy]. This means slow execution when the Windows Prism emulation system has to
    warm up its instruction caches.
    ```

    For all platforms, both a `pypy` placeholder (`#{<id>:pypy}`) and a `python` placeholder
    (`#{<id>:python}`) are supported and will be substituted with the selected distribution's PyPy
    interpreter binary path.

    [PyPy]: https://pypy.org/
    """

    @staticmethod
    def rank_compatibility(platform: Platform, arch: str) -> int | None:
        match platform:
            case Platform.Linux_s390x:
                match arch:
                    case "s390x":
                        return 0
            case Platform.Linux_aarch64:
                match arch:
                    case "aarch64-portable":
                        return 0
                    case "aarch64":
                        return 1
            case Platform.Linux_x86_64:
                match arch:
                    case "linux64":
                        return 0
            case Platform.Macos_aarch64:
                match arch:
                    case "macos_arm64":
                        return 0
            case Platform.Macos_x86_64:
                match arch:
                    case "macos_x86_64":
                        return 0
                    case "osx64":
                        return 1
            case Platform.Windows_aarch64 | Platform.Windows_x86_64:
                match arch:
                    case "win64":
                        return 0
                    case "win32":
                        return 1
        return None

    @classmethod
    def config_dataclass(cls) -> type[Config]:
        return Config

    @classmethod
    def create(cls, identifier: Identifier, lazy: bool, config: Config) -> PyPy:
        configured_version = Version(config.version)
        configured_release = config.release

        checksums_html = BeautifulSoup(
            fetch_text(url=Url("https://pypy.org/checksums.html"), ttl=timedelta(days=5)),
            features="html.parser",
        )
        assets = []
        for block in checksums_html.find_all(
            string=re.compile(r"^[a-f0-9]{64}\s+pypy\d+\.\d+-.*$", flags=re.DOTALL | re.MULTILINE)
        ):
            for line in block.splitlines():
                match = re.match(
                    r"^\s*(?P<fingerprint>[a-f0-9]{64})\s+"
                    r"(?P<name>"
                    r"pypy(?P<version>\d+\.\d+)-"
                    r"(?P<release>v[^-]+)-"
                    r"(?P<arch>[^.]+)\."
                    r"(?P<extension>.+)"
                    r")",
                    line,
                )
                if not match:
                    continue

                version = Version(match["version"])
                if configured_version != version:
                    continue

                release = match["release"]
                if configured_release and configured_release != release:
                    continue

                name = match["name"]
                extension = match["extension"]
                assets.append(
                    FingerprintedAsset(
                        url=Url(f"https://downloads.python.org/pypy/{name}"),
                        name=name,
                        extension=extension,
                        version=version,
                        release=release,
                        arch=match["arch"],
                        fingerprint=Fingerprint(match["fingerprint"]),
                        file_type=FileType.for_extension(extension),
                    )
                )

        return PyPy(id=identifier, lazy=lazy, assets=tuple(assets))

    id: Identifier
    lazy: bool
    assets: tuple[FingerprintedAsset, ...]

    def distribution(self, platform: Platform) -> Distribution | None:
        selected_asset: FingerprintedAsset | None = None
        asset_rank: int | None = None
        for asset in self.assets:
            if (rank := self.rank_compatibility(platform, asset.arch)) is not None and (
                asset_rank is None or rank < asset_rank
            ):
                asset_rank = rank
                selected_asset = asset
        if selected_asset is None:
            raise InputError(
                f"No compatible distribution was found for {platform} from amongst:\n"
                f"{os.linesep.join(asset.name for asset in self.assets)}"
            )

        size = int(
            configured_client(selected_asset.url).head(selected_asset.url).headers["Content-Length"]
        )

        file = File(
            name=selected_asset.name,
            key=self.id,
            digest=Digest(size=size, fingerprint=selected_asset.fingerprint),
            type=selected_asset.file_type,
            is_executable=False,
            eager_extract=False,
            source=Fetch(url=Url(selected_asset.url), lazy=self.lazy),
        )

        placeholders = {}
        pypy = (
            "pypy" if 2 == selected_asset.version.major else f"pypy{selected_asset.version.major}"
        )

        # These 4 distributions are the only distributions with `-portable` in the archive name, but
        # not in the top level archive dir name:
        # pypy2.7-v7.3.8-aarch64-portable.tar.bz2
        # pypy3.7-v7.3.8-aarch64-portable.tar.bz2
        # pypy3.8-v7.3.8-aarch64-portable.tar.bz2
        # pypy3.9-v7.3.8-aarch64-portable.tar.bz2
        #
        # We correct for that discrepency here:
        top_level_archive_dir = re.sub(r"-portable$", "", selected_asset.file_stem())

        match platform:
            case Platform.Windows_aarch64 | Platform.Windows_x86_64:
                pypy_binary = f"{top_level_archive_dir}\\{pypy}.exe"
                placeholders[Identifier("pypy")] = pypy_binary
                placeholders[Identifier("python")] = pypy_binary
            case _:
                pypy_binary = f"{top_level_archive_dir}/bin/{pypy}"
                placeholders[Identifier("pypy")] = pypy_binary
                placeholders[Identifier("python")] = pypy_binary

        return Distribution(id=self.id, file=file, placeholders=FrozenDict(placeholders))

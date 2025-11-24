# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).


import dataclasses
import json
import re
import urllib.parse
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

from bs4 import BeautifulSoup
from packaging.version import Version

from science.cache import Missing, download_cache
from science.dataclass.reflect import metadata
from science.fetcher import configured_client, fetch_json, fetch_text
from science.frozendict import FrozenDict
from science.hashing import Digest, Fingerprint
from science.model import (
    Distribution,
    DistributionsManifest,
    Fetch,
    File,
    FileType,
    Identifier,
    Provider,
    Url,
)
from science.platform import LibC, Platform, PlatformSpec


@dataclass(frozen=True)
class FingerprintedAsset:
    @classmethod
    def from_dict(cls, data: dict[str, Any], base_url: Url) -> FingerprintedAsset:
        data["url"] = Url(
            f"{base_url.rstrip('/')}/{urllib.parse.quote_plus(data.pop('rel_path'), safe='/')}"
        )
        data["version"] = Version(data["version"])
        data["fingerprint"] = Fingerprint(data["fingerprint"])
        data["file_type"] = FileType(data["file_type"])
        return cls(**data)

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

    def as_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["rel_path"] = data.pop("url").rel_path.as_posix()
        data["version"] = str(data["version"])
        data["file_type"] = data["file_type"].value
        return data


@dataclass(frozen=True)
class Distributions:
    @classmethod
    def fetch(cls, base_url: Url, version: Version, release: str | None = None) -> Distributions:
        data = fetch_json(
            Url(f"{base_url.rstrip('/')}/distributions-{version}-{release or 'any'}.json")
        )
        return cls(
            base_url=base_url,
            version=version,
            release=release,
            assets=tuple(
                FingerprintedAsset.from_dict(asset, base_url=base_url) for asset in data["assets"]
            ),
        )

    base_url: Url
    version: Version
    release: str | None
    assets: tuple[FingerprintedAsset, ...]

    def serialize(self, base_dir: Path) -> None:
        base_dir.mkdir(parents=True, exist_ok=True)
        with (base_dir / f"distributions-{self.version}-{self.release or 'any'}.json").open(
            "w"
        ) as fp:
            json.dump(
                {"base_url": self.base_url, "assets": [asset.as_dict() for asset in self.assets]},
                fp,
                sort_keys=True,
                indent=2,
            )


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
    base_url: Url | None = dataclasses.field(
        default=None,
        metadata=metadata(
            """The base URL to download distributions from.

            Defaults to https://downloads.python.org/pypy/ but can be configured to the
            `providers/PyPy` sub-directory of a mirror created with the
            `science download provider PyPy` command.
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

    @classmethod
    def iter_supported_platforms(
        cls, requested_platforms: Iterable[PlatformSpec]
    ) -> Iterator[PlatformSpec]:
        for platform_spec in requested_platforms:
            if platform_spec.platform in (
                Platform.Linux_aarch64,
                Platform.Linux_s390x,
                Platform.Macos_aarch64,
                Platform.Macos_x86_64,
                Platform.Windows_aarch64,
                Platform.Windows_x86_64,
            ):
                yield PlatformSpec(platform_spec.platform)
            elif platform_spec.platform is Platform.Linux_x86_64:
                yield PlatformSpec(Platform.Linux_x86_64, LibC.GLIBC)

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
        if config.base_url:
            return cls(
                id=identifier,
                lazy=lazy,
                _distributions=Distributions.fetch(
                    base_url=config.base_url, version=configured_version, release=config.release
                ),
            )

        configured_release = config.release

        base_url = Url("https://downloads.python.org/pypy")
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
                        url=Url(f"https://downloads.python.org/pypy/{name}", base=base_url),
                        name=name,
                        extension=extension,
                        version=version,
                        release=release,
                        arch=match["arch"],
                        fingerprint=Fingerprint(match["fingerprint"]),
                        file_type=FileType.for_extension(extension),
                    )
                )

        return cls(
            id=identifier,
            lazy=lazy,
            _distributions=Distributions(
                base_url=base_url,
                version=configured_version,
                release=configured_release,
                assets=tuple(assets),
            ),
        )

    id: Identifier
    lazy: bool
    _distributions: Distributions

    @property
    def version(self) -> Version:
        return self._distributions.version

    def distributions(self) -> DistributionsManifest:
        return self._distributions

    def distribution(self, platform_spec: PlatformSpec) -> Distribution | None:
        selected_asset: FingerprintedAsset | None = None
        asset_rank: int | None = None
        for asset in self._distributions.assets:
            if (
                rank := self.rank_compatibility(platform_spec.platform, asset.arch)
            ) is not None and (asset_rank is None or rank < asset_rank):
                asset_rank = rank
                selected_asset = asset
        if selected_asset is None:
            return None

        with download_cache().get_or_create(url=Url(f"{selected_asset.url}.size")) as cache_result:
            if isinstance(cache_result, Missing):
                with configured_client(selected_asset.url) as client:
                    response = client.head(selected_asset.url)
                size = int(response.headers["Content-Length"].strip())
                cache_result.work_path.write_text(str(size))
            else:
                size = int(cache_result.path.read_text())

        file = File(
            name=selected_asset.name,
            key=self.id,
            digest=Digest(size=size, fingerprint=selected_asset.fingerprint),
            type=selected_asset.file_type,
            is_executable=False,
            eager_extract=False,
            source=Fetch(
                url=Url(selected_asset.url, base=self._distributions.base_url), lazy=self.lazy
            ),
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

        if platform_spec.is_windows:
            pypy_binary = f"{top_level_archive_dir}\\{pypy}.exe"
            placeholders[Identifier("pypy")] = pypy_binary
            placeholders[Identifier("python")] = pypy_binary
        else:
            pypy_binary = f"{top_level_archive_dir}/bin/{pypy}"
            placeholders[Identifier("pypy")] = pypy_binary
            placeholders[Identifier("python")] = pypy_binary

        return Distribution(id=self.id, file=file, placeholders=FrozenDict(placeholders))

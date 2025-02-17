# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import json
import re
import urllib.parse
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path, PurePath
from typing import Any

from packaging.version import Version

from science.cache import download_cache
from science.dataclass.reflect import metadata
from science.errors import InputError
from science.fetcher import fetch_json, fetch_text
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
            f"{base_url.rstrip("/")}/{urllib.parse.quote_plus(data.pop("rel_path"), safe="/")}"
        )

        digest = data["digest"]
        data["digest"] = Digest(size=digest["size"], fingerprint=Fingerprint(digest["fingerprint"]))

        data["version"] = Version(data["version"])
        data["file_type"] = FileType(data["file_type"])
        return cls(**data)

    url: Url
    name: str
    digest: Digest
    version: Version
    target_triple: str
    file_type: FileType

    def as_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["rel_path"] = data.pop("url").rel_path.as_posix()
        data["digest"] = {"size": self.digest.size, "fingerprint": self.digest.fingerprint}
        data["version"] = str(data["version"])
        data["file_type"] = data["file_type"].value
        return data


@dataclass(frozen=True)
class Distributions:
    @classmethod
    def fetch(
        cls, base_url: Url, version: Version, flavor: str, release: str | None = None
    ) -> Distributions:
        rel_path = (
            PurePath(f"download/{release}" if release else "latest/download")
            / f"distributions-{version}-{flavor}.json"
        )
        data = fetch_json(Url(f"{base_url.rstrip("/")}/{rel_path.as_posix()}"))
        return cls(
            base_url=base_url,
            release=data["release"],
            latest=release is None,
            version=version,
            flavor=flavor,
            assets=tuple(
                FingerprintedAsset.from_dict(asset, base_url=base_url) for asset in data["assets"]
            ),
        )

    base_url: Url
    release: str
    latest: bool
    version: Version
    flavor: str
    assets: tuple[FingerprintedAsset, ...]

    def serialize(self, base_dir: Path) -> None:
        if self.latest:
            dest_dir = base_dir / "latest" / "download"
        else:
            dest_dir = base_dir / "download" / self.release
        dest_dir.mkdir(parents=True, exist_ok=True)
        with (dest_dir / f"distributions-{self.version}-{self.flavor}.json").open("w") as fp:
            json.dump(
                {
                    "base_url": self.base_url,
                    "release": self.release,
                    "assets": [asset.as_dict() for asset in self.assets],
                },
                fp,
                sort_keys=True,
                indent=2,
            )


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
            [their releases](https://github.com/astral-sh/python-build-standalone/releases) if you
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

            [releases-page]: https://github.com/astral-sh/python-build-standalone/releases
            """
        ),
    )
    libc: LibC | None = dataclasses.field(
        default=None,
        metadata=metadata("For Linux x86_64 platforms, the libc to link against."),
    )
    flavor: str = dataclasses.field(
        default="install_only",
        metadata=metadata(
            """The flavor of the Python Standalone Builds release to use.

            Currently only accepts 'install_only' and 'install_only_stripped'.
            """
        ),
    )
    base_url: Url | None = dataclasses.field(
        default=None,
        metadata=metadata(
            """The base URL to download distributions from.

            Defaults to https://github.com/astral-sh/python-build-standalone/releases but can be
            configured to the `providers/PythonBuildStandalone` sub-directory of a mirror created
            with the `science download provider PythonBuildStandalone` command.
            """
        ),
    )


@dataclass(frozen=True)
class PythonBuildStandalone(Provider[Config]):
    """Provides distributions from the [Python Standalone Builds][PBS] project.

    All science platforms are supported for Python 3 minor versions >= 8.

    ```{note}
    Windows ARM64 uses the x86-64 binaries since there are currently no Windows ARM64 releases
    from [Python Standalone Builds][PBS]. This means slow execution when the Windows Prism
    emulation system has to warm up its instruction caches.
    ```

    For all platforms, a `python` placeholder (`#{<id>:python}`) is supported and will be
    substituted with the selected distribution's Python binary path.

    On the Linux and macOS platforms a `pip` placeholder (`#{<id>:pip}`) is supported and will be
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

    Note that Python Standalone Builds distributions come with some [quirks] that you should probably
    familiarize yourself with to make sure your application runs correctly under them.

    ```{warning}
    One known quirk revolves around the statically linked OpenSSL Python Standalone Builds
    distributions ship with. These are compiled from official OpenSSL releases which can be a
    problem when run on machines that have their own patched version of OpenSSL that reads custom
    OpenSSL configuration data (e.g.: from `/etc/ssl/openssl.cnf`). Normally, OpenSSL errors for
    configuration options it does not understand, but, due to a quirk in the CPython `ssl` module,
    most Python applications will have OpenSSL configuration errors masked and continue to run with
    partially applied OpenSSL config. This may have security implications for your application.

    For more on this see:
    https://github.com/astral-sh/python-build-standalone/issues/207
    ```

    [PBS]: https://gregoryszorc.com/docs/python-build-standalone/main
    [quirks]: https://gregoryszorc.com/docs/python-build-standalone/main/quirks.html
    """

    @staticmethod
    def rank_compatibility(platform: Platform, libc: LibC, target_triple: str) -> int | None:
        match platform:
            case Platform.Linux_aarch64:
                match target_triple:
                    case "aarch64-unknown-linux-gnu":
                        return 0
            case Platform.Linux_armv7l:
                match target_triple:
                    case "armv7-unknown-linux-gnueabihf":
                        return 0
                    case "armv7-unknown-linux-gnueabi":
                        return 1
            case Platform.Linux_powerpc64le:
                match target_triple:
                    case "ppc64le-unknown-linux-gnu":
                        return 0
            case Platform.Linux_s390x:
                match target_triple:
                    case "s390x-unknown-linux-gnu":
                        return 0
            case Platform.Linux_x86_64:
                match libc, target_triple:
                    case LibC.MUSL, "x86_64-unknown-linux-musl":
                        return 0
                    case LibC.GLIBC, "x86_64-unknown-linux-gnu":
                        return 0
                    case LibC.GLIBC, "x86_64_v2-unknown-linux-gnu":
                        return 1
                    case LibC.GLIBC, "x86_64_v3-unknown-linux-gnu":
                        return 2
                    case LibC.GLIBC, "x86_64_v4-unknown-linux-gnu":
                        return 3
            case Platform.Macos_aarch64:
                match target_triple:
                    case "aarch64-apple-darwin":
                        return 0
            case Platform.Macos_x86_64:
                match target_triple:
                    case "x86_64-apple-darwin":
                        return 0
            case Platform.Windows_aarch64 | Platform.Windows_x86_64:
                match target_triple:
                    # N.B.: The -shared tag was removed in
                    # https://github.com/astral-sh/python-build-standalone/releases/tag/20240415
                    # but the archive is still dynamically linked.
                    case "x86_64-pc-windows-msvc" | "x86_64-pc-windows-msvc-shared":
                        return 0
                    case "x86_64-pc-windows-msvc-static":
                        return 1
        return None

    @classmethod
    def config_dataclass(cls) -> type[Config]:
        return Config

    @classmethod
    def create(cls, identifier: Identifier, lazy: bool, config: Config) -> PythonBuildStandalone:
        version = Version(config.version)
        if config.base_url:
            return cls(
                id=identifier,
                lazy=lazy,
                libc=config.libc,
                _distributions=Distributions.fetch(
                    base_url=config.base_url,
                    version=version,
                    flavor=config.flavor,
                    release=config.release,
                ),
            )

        api_url = "https://api.github.com/repos/astral-sh/python-build-standalone/releases"
        if config.release:
            release_url = Url(f"{api_url}/tags/{config.release}")
            ttl = None
        else:
            release_url = Url(f"{api_url}/latest")
            ttl = timedelta(days=5)
        # For a given release (optional config parameter), get metadata.
        release_data = fetch_json(release_url, ttl=ttl)

        release = release_data["name"]
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
        base_url = Url("https://github.com/astral-sh/python-build-standalone/releases")
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
                    url=Url(url, base=base_url),
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
            libc=config.libc,
            _distributions=Distributions(
                release=release,
                latest=config.release is None,
                version=version,
                flavor=config.flavor,
                base_url=base_url,
                assets=tuple(fingerprinted_assets),
            ),
        )

    id: Identifier
    lazy: bool
    libc: LibC | None
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
                rank := self.rank_compatibility(
                    platform_spec.platform,
                    self.libc or platform_spec.libc or LibC.GLIBC,
                    asset.target_triple,
                )
            ) is not None and (asset_rank is None or rank < asset_rank):
                asset_rank = rank
                selected_asset = asset
        if selected_asset is None:
            return None

        file = File(
            name=selected_asset.name,
            key=self.id,
            digest=selected_asset.digest,
            type=selected_asset.file_type,
            is_executable=False,
            eager_extract=False,
            source=Fetch(
                url=Url(selected_asset.url, base=self._distributions.base_url), lazy=self.lazy
            ),
        )
        placeholders = {}
        match self._distributions.flavor:
            case "install_only" | "install_only_stripped":
                if platform_spec.is_windows:
                    placeholders[Identifier("python")] = "python\\python.exe"
                else:
                    version = f"{selected_asset.version.major}.{selected_asset.version.minor}"
                    placeholders[Identifier("python")] = f"python/bin/python{version}"
                    placeholders[Identifier("pip")] = f"python/bin/pip{version}"
            case flavor:
                raise InputError(
                    "PythonBuildStandalone currently only understands the 'install_only' flavor of "
                    f"distribution, given: {flavor}"
                )
        return Distribution(id=self.id, file=file, placeholders=FrozenDict(placeholders))

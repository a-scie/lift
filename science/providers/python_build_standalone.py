# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from frozendict import frozendict
from packaging.version import Version

from science.fetcher import fetch_json, fetch_text
from science.model import Digest, Distribution, File, FileType, Identifier, Provider
from science.platform import Platform


@dataclass(frozen=True)
class FingerprintedAsset:
    url: str
    name: str
    digest: Digest
    version: Version
    target_triple: str
    file_type: FileType


@dataclass(frozen=True)
class Asset:
    url: str
    name: str
    size: int
    version: str
    target_triple: str
    extension: str

    def with_fingerprint(self, fingerprint: str) -> FingerprintedAsset:
        return FingerprintedAsset(
            url=self.url,
            name=self.name,
            digest=Digest(size=self.size, fingerprint=fingerprint),
            version=Version(self.version),
            target_triple=self.target_triple,
            file_type=FileType.for_extension(self.extension),
        )


@dataclass(frozen=True)
class PBS(Provider):
    @classmethod
    def create(cls, identifier: Identifier, **kwargs) -> PBS:
        api_url = "https://api.github.com/repos/indygreg/python-build-standalone/releases"
        release_url = (
            f"{api_url}/tags/{release}"
            if (release := kwargs.get("release"))
            else f"{api_url}/latest"
        )
        release_data = fetch_json(release_url)

        release = release_data["name"]
        version = Version(kwargs["version"])
        flavor = kwargs.get("flavor", "install_only")

        # Names are like:
        #  cpython-3.9.16+20221220-x86_64_v3-unknown-linux-musl-install_only.tar.gz
        name_re = re.compile(
            rf"^cpython-(?P<exact_version>{re.escape(str(version))}(?:\.\d+)*)"
            rf"\+{re.escape(release)}-(?P<target_triple>.+)-{re.escape(flavor)}\.(?P<extension>.+)$"
        )

        # N.B.: There are 3 types of files in PBS releases:
        # 1. The release archive.
        # 2. The release archive .sah256 file with its individual checksum.
        # 3. The SHA256SUMS file with all the release archive checksums.
        sha256sums_url: str | None = None
        asset_mapping = {}
        for asset in release_data["assets"]:
            name = asset["name"]
            if "SHA256SUMS" == name:
                sha256sums_url = asset["browser_download_url"]
            elif name.endswith(".sha256"):
                continue
            elif match := name_re.match(name):
                url = asset["browser_download_url"]
                size = asset["size"]
                exact_version = match["exact_version"]
                target_triple = match["target_triple"]
                extension = match["extension"]
                asset_mapping[name] = Asset(
                    url=url,
                    name=name,
                    size=size,
                    version=exact_version,
                    target_triple=target_triple,
                    extension=extension,
                )

        if not sha256sums_url:
            raise ValueError(f"Did not find expected SHA256SUMS asset for release {release}.")

        sha256sums = {}
        for line in fetch_text(sha256sums_url).splitlines():
            if line := line.strip():
                fingerprint, name = re.split(r"\s+", line)
                sha256sums[name] = fingerprint

        fingerprinted_assets = []
        for name, asset in asset_mapping.items():
            fingerprint = sha256sums[name]
            fingerprinted_assets.append(asset.with_fingerprint(fingerprint))

        if not fingerprinted_assets:
            raise ValueError(
                f"No released assets found for release {release} Python {version} of flavor "
                f"{flavor}."
            )

        return cls(
            id=identifier,
            release=release,
            version=version,
            flavor=flavor,
            assets=tuple(fingerprinted_assets),
        )

    id: Identifier
    release: str
    version: Version
    flavor: str
    assets: tuple[FingerprintedAsset, ...]

    def distribution(self, platform: Platform) -> Distribution | None:
        selected_asset: FingerprintedAsset | None = None
        asset_rank: int | None = None
        for asset in self.assets:
            if (rank := platform.compatibility(asset.target_triple)) is not None and (
                asset_rank is None or rank > asset_rank
            ):
                selected_asset = asset
        if selected_asset is None:
            raise ValueError(
                f"No compatible distribution was found for {platform} from amongst:\n"
                f"{os.linesep.join(asset.name for asset in self.assets)}"
            )

        key = f"cpython-{selected_asset.version.major}.{selected_asset.version.minor}"
        file = File(
            name=selected_asset.name,
            key=key,
            digest=selected_asset.digest,
            type=selected_asset.file_type,
            is_executable=False,
            eager_extract=False,
            source="fetch",  # TODO(John Sirois): XXX: Implement lazy vs. no.
        )
        return Distribution(id=self.id, file=file, placeholders=frozendict({}))

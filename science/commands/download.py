# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import itertools
import logging
import shutil
from pathlib import Path
from typing import Any, Iterable, Iterator, Tuple

import click
from packaging.version import Version

from science import a_scie
from science.errors import InputError
from science.fetcher import fetch_and_verify
from science.model import Fetch, Identifier
from science.platform import Platform, PlatformSpec
from science.providers import ProviderInfo

logger = logging.getLogger(__name__)


def download_a_scie_executables(
    project_name: str,
    binary_name: str,
    versions: Iterable[Version | None],
    platforms: Iterable[Platform],
    dest_dir: Path,
) -> None:
    for version in versions or [None]:
        if version:
            dest = dest_dir / project_name / "download" / f"v{version}"
        else:
            dest = dest_dir / project_name / "latest" / "download"
        dest.mkdir(parents=True, exist_ok=True)
        for platform in platforms:
            binary = dest / platform.qualified_binary_name(binary_name)
            click.echo(
                f"Downloading {binary_name} {version or 'latest'} for {platform} to {binary}...",
                err=True,
            )
            result = a_scie.load_project_release(
                project_name=project_name,
                binary_name=binary_name,
                version=version,
                platform=platform,
            )
            shutil.copy(result.path, binary)
            binary.with_name(f"{binary.name}.sha256").write_text(
                f"{result.digest.fingerprint} *{binary.name}"
            )


def download_provider_distribution(
    provider_info: ProviderInfo,
    platform_specs: Iterable[PlatformSpec],
    explicit_platforms: bool,
    dest_dir: Path,
    **kwargs: list[Any],
) -> None:
    base_dir = dest_dir / "providers" / provider_info.name
    config_dataclass = provider_info.type.config_dataclass()
    defaults = {field.name: field.default for field in provider_info.config_fields()}

    def iter_values(name) -> Iterator[Tuple[str, Any]]:
        values = kwargs[name] or [defaults[name]]
        for value in values:
            yield name, value

    configs = [
        config_dataclass(**dict(params))
        for params in itertools.product(*(iter_values(name) for name in kwargs))
    ]
    for config in configs:
        provider = provider_info.type.create(Identifier("_"), lazy=False, config=config)

        # TODO(John Sirois): Consider paring down the set of distributions serialized to those we
        #  actually download. The issue this will introduce is merging partial download distribution
        #  manifests.
        distributions = provider.distributions()
        distributions.serialize(base_dir=base_dir)

        config_desc = " ".join(
            str(value)
            for field in provider_info.config_fields()
            if (value := getattr(config, field.name))
        )
        for platform_spec in provider.iter_supported_platforms(platform_specs):
            if dist := provider.distribution(platform_spec):
                assert isinstance(dist.file.source, Fetch), (
                    f"Expected {provider_info.name} to fetch distributions by URL but "
                    f"{config_desc} for {platform_spec} has a source of {dist.file.source}."
                )
                dest = base_dir / dist.file.source.url.rel_path
                click.echo(
                    f"Downloading {provider_info.name} {config_desc} for {platform_spec} to "
                    f"{dest}...",
                    err=True,
                )
                result = fetch_and_verify(
                    url=dist.file.source.url,
                    fingerprint=dist.file.digest,
                    executable=dist.file.is_executable,
                )
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(result.path, dest)
                exe_flag = "*" if dist.file.is_executable else " "
                dest.with_name(f"{dest.name}.sha256").write_text(
                    f"{result.digest.fingerprint} {exe_flag}{dest.name}"
                )
            elif explicit_platforms:
                raise InputError(
                    f"There is no {provider_info.name} {config_desc} for {platform_spec}."
                )
            else:
                click.secho(
                    f"There is no {provider_info.name} {config_desc} for {platform_spec}, "
                    f"skipping.",
                    fg="yellow",
                )

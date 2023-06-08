# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import dataclasses
import importlib.metadata
import inspect
import logging
import os
import sys
from dataclasses import dataclass
from functools import cached_property
from typing import Generic, Iterator, TypeVar

from science.dataclass import Dataclass
from science.dataclass.reflect import FieldInfo, dataclass_info
from science.errors import InputError
from science.model import Provider
from science.providers.python_build_standalone import PythonBuildStandalone

_BUILTIN_PROVIDER_TYPES = (PythonBuildStandalone,)


ConfigDataclass = TypeVar("ConfigDataclass", bound=Dataclass)


@dataclass(frozen=True)
class ProviderInfo(Generic[ConfigDataclass]):
    type: type[Provider[ConfigDataclass]]
    source: str
    short_name: str | None = None

    @cached_property
    def fully_qualified_name(self) -> str:
        return f"{self.type.__module__}.{self.type.__qualname__}"

    @cached_property
    def summary(self) -> str | None:
        if doc := inspect.getdoc(self.type):
            return inspect.cleandoc(doc).splitlines()[0].strip()
        return None

    @cached_property
    def description(self) -> str | None:
        if doc := inspect.getdoc(self.type):
            if desc := os.linesep.join(inspect.cleandoc(doc).splitlines()[1:]).strip():
                return desc
        return None

    def config_fields(self) -> tuple[FieldInfo, ...]:
        return dataclass_info(self.type.config_dataclass()).field_info


def iter_builtin_providers() -> Iterator[ProviderInfo]:
    for builtin_provider_type in _BUILTIN_PROVIDER_TYPES:
        yield ProviderInfo(
            type=builtin_provider_type,
            source="builtin",
            short_name=builtin_provider_type.__qualname__,
        )


def _iter_providers() -> Iterator[ProviderInfo]:
    providers_by_short_name = dict[str, ProviderInfo]()

    def track_short_name(provider_info: ProviderInfo) -> ProviderInfo:
        if provider_info.short_name:
            providers_by_short_name[provider_info.short_name] = provider_info
        return provider_info

    for provider_info in iter_builtin_providers():
        yield track_short_name(provider_info)

    for entry_point in importlib.metadata.entry_points().select(
        group="science.providers_by_short_name"
    ):
        provider_type = entry_point.load()
        source = (
            f"{entry_point.dist.name} {entry_point.dist.version}"
            if entry_point.dist
            else "unknown plugin"
        )
        if not issubclass(provider_type, Provider):
            raise InputError(
                f"All science.providers entrypoints must conform to the {Provider.__qualname__} "
                f"protocol. Found `{entry_point.name!r} = {provider_type.__qualname__!r}` in "
                f"{source} which does not."
            )

        provider_info = ProviderInfo(type=provider_type, source=source)
        if existing_entry := providers_by_short_name.get(entry_point.name):
            logging.warning(
                f"The Provider {provider_type.__qualname__} found in {source} has a short name of"
                f"{entry_point.name!r} that conflicts with Provider "
                f"{existing_entry.type.__qualname__} provided by {existing_entry.source}. Not "
                f"registering {provider_type.__qualname__} under a that short name"
            )
        else:
            provider_info = dataclasses.replace(provider_info, short_name=entry_point.name)

        yield track_short_name(provider_info)


ALL_PROVIDERS = tuple[ProviderInfo, ...](
    sorted(
        _iter_providers(),
        key=lambda provider_info: (
            provider_info.short_name or chr(sys.maxunicode),
            provider_info.fully_qualified_name,
        ),
    )
)


def get_provider(name: str) -> ProviderInfo | None:
    for provider_info in ALL_PROVIDERS:
        if name in (provider_info.short_name, provider_info.fully_qualified_name):
            return provider_info
    return None

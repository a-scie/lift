# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import importlib.metadata
import logging
from typing import Iterator, Mapping

from science.frozendict import FrozenDict
from science.model import Provider

from ..errors import InputError
from .python_build_standalone import PythonBuildStandalone

_BUILTIN_PROVIDER_TYPES = (PythonBuildStandalone,)


def _builtin_names(provider_type: type[Provider]) -> Iterator[str]:
    # Name builtins as `science.providers.<type name>`, e.g.:
    # `science.providers.PythonBuildStandalone`.
    yield provider_type.__name__
    yield f"{__name__}.{provider_type.__name__}"


def _builtin() -> Mapping[str, type[Provider]]:
    return {
        name: builtin_provider_type
        for builtin_provider_type in _BUILTIN_PROVIDER_TYPES
        for name in _builtin_names(builtin_provider_type)
    }


def _plugins() -> Mapping[str, tuple[str, type[Provider]]]:
    plugins = {name: ("builtins", provider_type) for name, provider_type in _builtin().items()}
    for entry_point in importlib.metadata.entry_points().select(group="science.providers"):
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

        plugin_entry = source, provider_type
        plugins[provider_type.__qualname__] = plugin_entry
        if existing_entry := plugins[entry_point.name]:
            provenance, existing_provider_type = existing_entry
            logging.warning(
                f"The Provider {provider_type.__qualname__} found in {source} has a short name of"
                f"{entry_point.name!r} that conflicts with Provider "
                f"{existing_provider_type.__qualname__} provided by {provenance}. Not registering "
                f"{provider_type.__qualname__} under a that short name"
            )
        else:
            plugins[entry_point.name] = provider_type
    return plugins


_PROVIDERS = FrozenDict(
    {name: provider_type for name, (_source, provider_type) in _plugins().items()}
)


def get_provider(name: str) -> type[Provider] | None:
    return _PROVIDERS.get(name)

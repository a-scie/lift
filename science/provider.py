# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

from typing import Type

from science.frozendict import FrozenDict
from science.model import Provider
from science.providers.python_build_standalone import PBS

_PROVIDERS = FrozenDict({"science.providers.PBS": PBS})


def get_provider(name: str) -> Type[Provider] | None:
    return _PROVIDERS.get(name)

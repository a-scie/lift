# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from importlib.metadata import EntryPoint
from typing import Callable, Generic, TypeVar

from science.dataclass import Dataclass
from science.types import fully_qualified_name

DOC_SITE_URL = "https://science.scie.app"


_D = TypeVar("_D", bound=Dataclass)


@dataclass(frozen=True)
class Ref(Generic[_D]):
    @classmethod
    @cache
    def _create_slug(cls) -> Callable[[type], str]:
        # This is an affordance for the Sphinx doc-site generation and is set up in `docs/conf.py`.
        if slugifier := os.environ.get("_SCIENCE_REF_SLUGIFIER"):
            return EntryPoint(name="", group="", value=slugifier).load()
        return fully_qualified_name

    type_: type[_D]

    def __str__(self) -> str:
        return self._create_slug()(self.type_)

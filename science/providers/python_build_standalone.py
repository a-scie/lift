# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

from dataclasses import dataclass

from science.model import Distribution, Provider
from science.platform import Platform


@dataclass(frozen=True)
class PBS(Provider):
    @classmethod
    def create(cls, **kwargs) -> PBS:
        # TODO(John Sirois): XXX: Validate this data against GH releases API / maybe allow version
        # to be just major / minor and figure out the patch.
        return cls(release=kwargs["release"], version=kwargs["version"], flavor=kwargs["flavor"])

    release: str
    version: str
    flavor: str

    def distribution(self, platform: Platform) -> Distribution | None:
        return None

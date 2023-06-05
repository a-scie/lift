# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Collection, Mapping, TypeVar, cast

from science.errors import InputError
from science.frozendict import FrozenDict
from science.hashing import Provenance

_T = TypeVar("_T")


@dataclass(frozen=True)
class Data:
    provenance: Provenance
    data: FrozenDict[str, Any]
    path: str = ""

    def config(self, key: str) -> str:
        return f"`[{self.path}] {key}`" if self.path else f"`[{key}]`"

    class Required(Enum):
        VALUE = auto()

    REQUIRED = Required.VALUE

    def get_data(self, key: str, default: dict[str, Any] | Required = REQUIRED) -> Data:
        data = self.get_value(
            key, expected_type=Mapping, default=default  # type: ignore[type-abstract]
        )
        return Data(
            provenance=self.provenance,
            data=FrozenDict(data),
            path=f"{self.path}.{key}" if self.path else key,
        )

    def get_str(self, key: str, default: str | Required = REQUIRED) -> str:
        return self.get_value(key, expected_type=str, default=default)

    def get_int(self, key: str, default: int | Required = REQUIRED) -> int:
        return self.get_value(key, expected_type=int, default=default)

    def get_float(self, key: str, default: float | Required = REQUIRED) -> float:
        return self.get_value(key, expected_type=float, default=default)

    def get_bool(self, key: str, default: bool | Required = REQUIRED) -> bool:
        return self.get_value(key, expected_type=bool, default=default)

    def get_list(
        self,
        key: str,
        expected_item_type: type[_T],
        default: list[_T] | Required = REQUIRED,
    ) -> list[_T]:
        value = self.get_value(
            key, expected_type=Collection, default=default  # type: ignore[type-abstract]
        )
        invalid_entries = OrderedDict(
            (index, item)
            for index, item in enumerate(value, start=1)
            if not isinstance(item, expected_item_type)
        )
        if invalid_entries:
            invalid_items = [
                f"item {index}: {item} of type {self._typename(type(item))}"
                for index, item in invalid_entries.items()
            ]
            raise InputError(
                f"Expected {self.config(key)} defined in {self.provenance.source} to be a list "
                f"with items of type {self._typename(expected_item_type)} but got "
                f"{len(invalid_entries)} out of {len(value)} entries of the wrong type:{os.linesep}"
                f"{os.linesep.join(invalid_items)}"
            )
        return cast(list[_T], value)

    def get_data_list(
        self,
        key: str,
        default: list[dict] | Required = REQUIRED,
    ) -> list[Data]:
        return [
            Data(
                provenance=self.provenance,
                data=FrozenDict(data),
                path=f"{self.path}.{key}[{index}]" if self.path else key,
            )
            for index, data in enumerate(
                self.get_list(key, expected_item_type=Mapping, default=default), start=1
            )
        ]

    @staticmethod
    def _typename(type_: type) -> str:
        return "toml table" if issubclass(type_, Mapping) else type_.__name__

    def get_value(self, key: str, expected_type: type[_T], default: _T | Required = REQUIRED) -> _T:
        if key not in self.data:
            if default is self.REQUIRED:
                raise InputError(
                    f"Expected {self.config(key)} of type {self._typename(expected_type)} to be "
                    f"defined in {self.provenance.source}."
                )
            return default

        value = self.data[key]
        if not isinstance(value, expected_type):
            raise InputError(
                f"Expected a {self._typename(expected_type)} for {self.config(key)} but found "
                f"{value} of type {self._typename(type(value))} in {self.provenance.source}."
            )
        return value

    def __bool__(self):
        return bool(self.data)

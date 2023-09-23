# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Collection, Iterator, Mapping, TypeVar

from science.errors import InputError
from science.frozendict import FrozenDict
from science.hashing import Provenance

_T = TypeVar("_T")


@dataclass
class Data:
    provenance: Provenance
    data: FrozenDict[str, Any]
    path: str = ""
    _unused_data: dict[str, Any] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self._unused_data = dict(self.data)

    def config(self, key: str) -> str:
        return f"`[{self.path}] {key}`" if self.path else f"`[{key}]`"

    class Required(Enum):
        VALUE = auto()

    REQUIRED = Required.VALUE

    def get_data(
        self, key: str, default: dict[str, Any] | Required = REQUIRED, used: bool = False
    ) -> Data:
        raw_data = self.get_value(
            key, expected_type=Mapping, default=default, used=used  # type: ignore[type-abstract]
        )
        data = Data(
            provenance=self.provenance,
            data=FrozenDict(raw_data),
            path=f"{self.path}.{key}" if self.path else key,
        )
        if not used:
            self._unused_data[key] = data
        return data

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
        used: bool = True,
    ) -> list[_T]:
        value = self.get_value(
            key, expected_type=Collection, default=default, used=used  # type: ignore[type-abstract]
        )

        items = []
        invalid_entries = {}
        for index, item in enumerate(value, start=1):
            if isinstance(item, expected_item_type):
                items.append(item)
            else:
                # As a last resort, see if the item is convertible to the expected_item_type via its constructor. This
                # supports Enum and similar types.
                try:
                    items.append(expected_item_type(item))  # type: ignore[call-arg]
                except (TypeError, ValueError):
                    invalid_entries[index] = item

        if invalid_entries:
            invalid_items = [
                f"item {index}: {item} of type {self._typename(type(item))}"
                for index, item in invalid_entries.items()
            ]
            expected_values = ""
            if issubclass(expected_item_type, Enum):
                expected_values = f" from {{{', '.join(repr(expected.value) for expected in expected_item_type)}}}"

            raise InputError(
                f"Expected {self.config(key)} defined in {self.provenance.source} to be a list "
                f"with items of type {self._typename(expected_item_type)}{expected_values} but got "
                f"{len(invalid_entries)} out of {len(value)} entries of the wrong type:{os.linesep}"
                f"{os.linesep.join(invalid_items)}"
            )
        return items

    def get_data_list(
        self,
        key: str,
        default: list[dict] | Required = REQUIRED,
    ) -> list[Data]:
        data_list = [
            Data(
                provenance=self.provenance,
                data=FrozenDict(data),
                path=f"{self.path}.{key}[{index}]" if self.path else key,
            )
            for index, data in enumerate(
                self.get_list(key, expected_item_type=Mapping, default=default, used=False), start=1
            )
        ]
        if data_list:
            self._unused_data[key] = data_list
        return data_list

    @staticmethod
    def _typename(type_: type) -> str:
        return "toml table" if issubclass(type_, Mapping) else type_.__name__

    def get_value(
        self,
        key: str,
        expected_type: type[_T],
        default: _T | Required = REQUIRED,
        used: bool = True,
    ) -> _T:
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
        if used:
            self._unused_data.pop(key, None)
        return value

    def iter_unused_items(self) -> Iterator[tuple[str, Any]]:
        for key, value in self._unused_data.items():
            if isinstance(value, list) and all(isinstance(item, Data) for item in value):
                for index, item in enumerate(value, start=1):
                    for sub_key, sub_value in item.iter_unused_items():
                        yield f"{key}[{index}].{sub_key}", sub_value
            elif isinstance(value, Data):
                for sub_key, sub_value in value.iter_unused_items():
                    yield f"{key}.{sub_key}", sub_value
            else:
                yield key, value

    def __bool__(self):
        return bool(self.data)

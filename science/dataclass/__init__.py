# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

from typing import Any, ClassVar, Protocol, TypeVar


class Dataclass(Protocol):
    __dataclass_fields__: ClassVar[dict]


class DocumentedDataclass(Dataclass):
    __documented_dataclass__: ClassVar


_D = TypeVar("_D", bound=Dataclass)


def document_dataclass(data_type: type[_D], documentation: Any) -> type[_D]:
    setattr(data_type, "__documented_dataclass__", documentation)
    return data_type


_T = TypeVar("_T")


def get_documentation(data_type: type[_D], default: _T) -> _T:
    documentation = getattr(data_type, "__documented_dataclass__", default)
    expected_type = type(default)
    if not isinstance(documentation, expected_type):
        raise TypeError(
            f"Expected documentation on {data_type.__name__} to be of type {expected_type} but "
            f"was of type {type(documentation)}: {documentation}"
        )
    return documentation

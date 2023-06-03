# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import inspect
import os
import typing
from dataclasses import dataclass
from functools import cached_property
from types import NoneType, UnionType
from typing import ClassVar, Generic, Iterator, Protocol, Type, TypeVar, cast

from science.errors import InputError


class Dataclass(Protocol):
    __dataclass_fields__: ClassVar[dict]


_T = TypeVar("_T")
_D = TypeVar("_D", bound=Dataclass)


@dataclass(frozen=True)
class TypeInfo(Generic[_T]):
    type_: Type[_T]

    @cached_property
    def origin_types(self) -> tuple[type, ...]:
        def iter_origin_types() -> Iterator[type]:
            if isinstance(self.type_, UnionType):
                yield from typing.get_args(self.type_)
            else:
                yield typing.get_origin(self.type_) or self.type_

        return tuple(iter_origin_types())

    @cached_property
    def optional(self) -> bool:
        return any(typ is NoneType for typ in self.origin_types)

    @property
    def has_origin_type(self) -> bool:
        return len(self.origin_types) == 1

    @cached_property
    def origin_type(self) -> type[_T]:
        if not self.has_origin_type:
            raise InputError(
                os.linesep.join(
                    (
                        f"Cannot determine an origin type for {self} with {len(self.origin_types)} "
                        "origin types:",
                        os.linesep.join(
                            f"+ {origin_type.__name__}" for origin_type in self.origin_types
                        ),
                    )
                )
            )
        return cast(type[_T], self.origin_types[0])

    @cached_property
    def item_type(self) -> type:
        type_args = typing.get_args(self.type_)
        if self.issubtype(tuple):
            type_args = tuple({type_arg for type_arg in type_args if type_arg is not Ellipsis})
        if len(type_args) != 1:
            raise InputError(f"The {self.type_} type does not have a single item type: {type_args}")
        return type_args[0]

    @cached_property
    def dataclass(self) -> type[_D] | None:
        if len(self.origin_types) == 1 and dataclasses.is_dataclass(self.origin_type):
            return cast(type[_D], self.origin_type)
        return None

    def istype(self, expected_type: type) -> bool:
        return any(typ is expected_type for typ in self.origin_types)

    def issubtype(self, expected_type: type) -> type | None:
        for typ in self.origin_types:
            if typ is expected_type or inspect.isclass(typ) and issubclass(typ, expected_type):
                return typ
        return None

    def iter_types(self) -> Iterator[TypeInfo]:
        if isinstance(self.type_, UnionType):
            for typ in typing.get_args(self.type_):
                yield TypeInfo(typ)
        else:
            yield self

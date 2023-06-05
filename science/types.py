# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import inspect
import os
import typing
from dataclasses import dataclass
from functools import cached_property
from types import GenericAlias, NoneType, UnionType
from typing import Generic, Iterator, TypeVar, cast

from science.dataclass import Dataclass
from science.errors import InputError


def fully_qualified_name(type_: type) -> str:
    return f"{type_.__module__}.{type_.__qualname__}"


_T = TypeVar("_T")
_D = TypeVar("_D", bound=Dataclass)


@dataclass(frozen=True)
class TypeInfo(Generic[_T]):
    type_: type[_T]

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

    @cached_property
    def has_origin_type(self) -> bool:
        return len([typ for typ in self.origin_types if typ is not NoneType]) == 1

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
        return cast(type[_T], [typ for typ in self.origin_types if typ is not NoneType][0])

    @cached_property
    def has_item_type(self) -> bool:
        try:
            return self.item_type is not None
        except InputError:
            return False

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
        if self.has_origin_type and dataclasses.is_dataclass(self.origin_type):
            return cast(type[_D], self.origin_type)
        return None

    def istype(self, expected_type: type) -> bool:
        return any(typ is expected_type for typ in self.origin_types)

    def issubtype(self, *expected_types: type) -> type | None:
        for typ in self.origin_types:
            if typ in expected_types or inspect.isclass(typ) and issubclass(typ, expected_types):
                return typ
        return None

    def iter_types(self) -> Iterator[TypeInfo]:
        if isinstance(self.type_, UnionType):
            for typ in typing.get_args(self.type_):
                if typ is not NoneType:
                    yield TypeInfo(typ)
        else:
            yield self

    def iter_parameter_types(self) -> Iterator[TypeInfo]:
        for typ in typing.get_args(self.type_):
            yield TypeInfo(typ)

    def __str__(self) -> str:
        return (
            str(self.type_)
            if isinstance(self.type_, (GenericAlias, UnionType))
            else self.type_.__name__
        )

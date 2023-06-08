# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import inspect
import os
import typing
from dataclasses import MISSING, dataclass
from functools import cache, cached_property
from importlib.metadata import EntryPoint
from typing import (
    Any,
    Callable,
    ClassVar,
    Generic,
    Iterator,
    Mapping,
    TypeVar,
    cast,
    dataclass_transform,
)

from science.dataclass import Dataclass, document_dataclass, get_documentation
from science.types import TypeInfo, fully_qualified_name

_FIELD_METADATA_KEY = f"{__name__}.field_metadata"


@dataclass(frozen=True)
class FieldMetadata:
    DEFAULT: ClassVar[FieldMetadata]

    _doc: str | None = None
    reference: bool = False
    inline: bool = False
    hidden: bool = False

    @cached_property
    def doc(self) -> str | None:
        return inspect.cleandoc(self._doc) if self._doc else None


FieldMetadata.DEFAULT = FieldMetadata()


def metadata(
    doc: str | None = None, *, reference: bool = False, inline: bool = False, hidden: bool = False
) -> Mapping[str, FieldMetadata]:
    return {
        _FIELD_METADATA_KEY: FieldMetadata(
            _doc=doc, reference=reference, inline=inline, hidden=hidden
        )
    }


@dataclass(frozen=True)
class ClassMetadata:
    DEFAULT: ClassVar[ClassMetadata]

    alias: str | None = None


ClassMetadata.DEFAULT = ClassMetadata()


_T = TypeVar("_T")


@dataclass_transform()
def documented_dataclass(
    doc: str = "",
    *,
    alias: str | None = None,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool = False,
    match_args: bool = True,
    kw_only: bool = False,
    slots: bool = False,
    weakref_slot: bool = False,
) -> Callable[[type[_T]], type[_D]]:
    def wrapper(cls: type[_T]) -> type[_D]:
        data_type = typing.cast(
            type[_D],
            dataclass(
                init=init,
                repr=repr,
                eq=eq,
                order=order,
                unsafe_hash=unsafe_hash,
                frozen=frozen,
                match_args=match_args,
                kw_only=kw_only,
                slots=slots,
                weakref_slot=weakref_slot,
            )(cls),
        )
        if doc:
            data_type.__doc__ = doc
        return document_dataclass(data_type, ClassMetadata(alias=alias))

    return wrapper


_D = TypeVar("_D", bound=Dataclass)


@dataclass(frozen=True)
class Ref(Generic[_D]):
    @classmethod
    @cache
    def _create_slug(cls) -> Callable[[type], str]:
        slugifier = os.environ.get("_SCIENCE_REF_SLUGIFIER")
        if slugifier:
            return EntryPoint(name="", group="", value=slugifier).load()
        return fully_qualified_name

    type_: type[_D]

    def __str__(self) -> str:
        return self._create_slug()(self.type_)


_F = TypeVar("_F")


@dataclass(frozen=True)
class FieldInfo(Generic[_F]):
    name: str
    type: TypeInfo[_F]
    default: Any
    doc: str | None
    reference: bool
    inline: bool = False
    hidden: bool = False

    @property
    def has_default(self) -> bool:
        return self.default is not MISSING


@dataclass(frozen=True)
class DataclassInfo(Generic[_D]):
    type: type[_D]
    alias: str | None
    field_info: tuple[FieldInfo, ...] = ()

    @property
    def name(self) -> str:
        return self.alias or self.type.__name__

    @cached_property
    def doc(self) -> str | None:
        if doc := inspect.getdoc(self.type):
            # Unfortunately, @dataclass automatically generates __doc__ with no way to turn it off.
            # The generated doc, though, is very nearly == inspect.signature of the @dataclass type.
            if f"{doc} -> None" != f"{self.type.__name__}{inspect.signature(self.type)}":
                return inspect.cleandoc(doc).strip()
        return None


@cache
def dataclass_info(data_type: type[_D]) -> DataclassInfo[_D]:
    class_metadata = get_documentation(data_type, ClassMetadata.DEFAULT)

    def iter_field_info() -> Iterator[FieldInfo]:
        type_hints = typing.get_type_hints(data_type)
        for field in dataclasses.fields(data_type):
            field_metadata = field.metadata.get(_FIELD_METADATA_KEY, FieldMetadata.DEFAULT)
            yield FieldInfo(
                name=field.name,
                type=TypeInfo(type_hints.get(field.name, field.type)),
                default=field.default,
                doc=field_metadata.doc,
                reference=field_metadata.reference,
                inline=field_metadata.inline,
                hidden=field_metadata.hidden,
            )

    return DataclassInfo(
        type=data_type, alias=class_metadata.alias, field_info=tuple(iter_field_info())
    )


def iter_dataclass_info(
    data_type: type[_D], include_hidden: bool = True, include_inlined: bool = True
) -> Iterator[DataclassInfo]:
    data_type_info = dataclass_info(data_type)
    yield data_type_info
    for field_info in data_type_info.field_info:
        if not include_hidden and field_info.hidden:
            continue
        if not include_inlined and field_info.inline:
            continue
        for origin_type in field_info.type.origin_types:
            if dataclasses.is_dataclass(origin_type):
                yield from iter_dataclass_info(
                    cast(type[Dataclass], origin_type),
                    include_hidden=include_hidden,
                    include_inlined=include_inlined,
                )
        if field_info.type.has_item_type and dataclasses.is_dataclass(field_info.type.item_type):
            yield from iter_dataclass_info(
                cast(type[Dataclass], field_info.type.item_type),
                include_hidden=include_hidden,
                include_inlined=include_inlined,
            )

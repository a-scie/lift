# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import inspect
import typing
from dataclasses import MISSING, dataclass
from functools import cache, cached_property
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
from science.types import TypeInfo

_FIELD_METADATA_KEY = f"{__name__}.field_metadata"


@dataclass(frozen=True)
class FieldMetadata:
    DEFAULT: ClassVar[FieldMetadata]

    alias: str | None = None
    doc_func: Callable[[], str] | None = None
    reference: bool = False
    inline: bool = False
    hidden: bool = False

    @cached_property
    def doc(self) -> str:
        return inspect.cleandoc(self.doc_func()) if self.doc_func else ""


FieldMetadata.DEFAULT = FieldMetadata()


def metadata(
    doc: str | Callable[[], str] = "",
    *,
    alias: str | None = None,
    reference: bool = False,
    inline: bool = False,
    hidden: bool = False,
) -> Mapping[str, FieldMetadata]:
    if isinstance(doc, str):

        def doc_func() -> str:
            return doc
    else:
        doc_func = doc

    return {
        _FIELD_METADATA_KEY: FieldMetadata(
            alias=alias, doc_func=doc_func, reference=reference, inline=inline, hidden=hidden
        )
    }


@dataclass(frozen=True)
class ClassMetadata:
    DEFAULT: ClassVar[ClassMetadata]

    alias: str | None = None
    doc_func: Callable[[], str] | None = None

    @cached_property
    def doc(self) -> str:
        return inspect.cleandoc(self.doc_func()) if self.doc_func else ""


ClassMetadata.DEFAULT = ClassMetadata()


_T = TypeVar("_T")


@dataclass_transform()
def documented_dataclass(
    doc: str | Callable[[], str] = "",
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

        if not doc:

            def doc_func() -> str:
                if doc_ := inspect.getdoc(data_type):
                    # Unfortunately, @dataclass automatically generates __doc__ with no way to turn
                    # it off. The generated doc, though, is very nearly == inspect.signature of the
                    # @dataclass type.
                    if f"{doc_} -> None" != f"{data_type.__name__}{inspect.signature(data_type)}":
                        return inspect.cleandoc(doc_)
                return ""

        elif isinstance(doc, str):

            def doc_func() -> str:
                return cast(str, doc)
        else:
            doc_func = doc

        return document_dataclass(data_type, ClassMetadata(alias=alias, doc_func=doc_func))

    return wrapper


_F = TypeVar("_F")


@dataclass(frozen=True)
class FieldInfo(Generic[_F]):
    name: str
    alias: str | None
    type: TypeInfo[_F]
    default: Any
    doc: str
    reference: bool
    inline: bool = False
    hidden: bool = False

    @property
    def display_name(self) -> str:
        return self.alias or self.name

    @property
    def has_default(self) -> bool:
        return self.default is not MISSING


_D = TypeVar("_D", bound=Dataclass)


@dataclass(frozen=True)
class DataclassInfo(Generic[_D]):
    type: type[_D]
    alias: str | None
    doc: str
    field_info: tuple[FieldInfo, ...] = ()

    @property
    def name(self) -> str:
        return self.alias or self.type.__name__


@cache
def dataclass_info(data_type: type[_D]) -> DataclassInfo[_D]:
    class_metadata = get_documentation(data_type, ClassMetadata.DEFAULT)

    def iter_field_info() -> Iterator[FieldInfo]:
        type_hints = typing.get_type_hints(data_type)
        for field in dataclasses.fields(data_type):
            field_metadata = field.metadata.get(_FIELD_METADATA_KEY, FieldMetadata.DEFAULT)
            yield FieldInfo(
                name=field.name,
                alias=field_metadata.alias,
                type=TypeInfo(type_hints.get(field.name, field.type)),
                default=field.default,
                doc=field_metadata.doc,
                reference=field_metadata.reference,
                inline=field_metadata.inline,
                hidden=field_metadata.hidden,
            )

    return DataclassInfo(
        type=data_type,
        alias=class_metadata.alias,
        doc=class_metadata.doc,
        field_info=tuple(iter_field_info()),
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

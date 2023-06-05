# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import os
from collections import deque
from dataclasses import dataclass
from enum import Enum
from types import NoneType
from typing import Any, Callable, Collection, Iterator, Mapping, Self

from docutils import nodes
from sphinx_science import directives
from sphinx_science.directives import bool_option
from sphinx_science.render import MarkdownParser, Section

from science.dataclass import Dataclass
from science.dataclass.reflect import (
    DataclassInfo,
    FieldInfo,
    dataclass_info,
    documented_dataclass,
)
from science.frozendict import FrozenDict
from science.types import TypeInfo


@dataclass(frozen=True)
class TOMLType:
    label: str

    def render_value(self, value: Any) -> str:
        return repr(value)


@dataclass(frozen=True)
class PrimitiveType(TOMLType):
    def render_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return repr(value)


@dataclass(frozen=True)
class ArrayType(TOMLType):
    @classmethod
    def create(cls, item_type: TOMLType) -> Self:
        return cls(label=f"Array[{item_type.label}]", item_type=item_type)

    item_type: TOMLType

    def render_value(self, value: Any) -> str:
        return repr([self.item_type.render_value(item) for item in value])


@dataclass(frozen=True)
class TableType(TOMLType):
    @classmethod
    def create(cls, value_type: TOMLType) -> Self:
        return cls(label=f"Table[Key, {value_type.label}]", value_type=value_type)

    value_type: TOMLType | None = None

    def render_value(self, value: Any) -> str:
        if self.value_type:
            return repr({key: self.value_type.render_value(val) for key, val in value.items()})
        return repr(value)


@dataclass(frozen=True)
class ChoiceType(TOMLType):
    @classmethod
    def for_enum(
        cls, enum_type: type[Enum], toml_type_factory: Callable[[type | TypeInfo], TOMLType]
    ) -> Self:
        choices = tuple(choice.value for choice in enum_type)
        choice_types = set(type(choice) for choice in choices)
        assert len(choice_types) == 1
        choice_type = toml_type_factory(choice_types.pop())
        return cls(
            label=" | ".join(f"{choice_type.render_value(choice)}" for choice in choices),
            renderer=lambda value: enum_type(value).value,
        )

    renderer: Callable[[Any], str]

    def render_value(self, value: Any) -> str:
        return self.renderer(value)


@dataclass(frozen=True)
class UnionType(TOMLType):
    @classmethod
    def for_type_info(
        cls, type_info: TypeInfo, toml_type_factory: Callable[[type | TypeInfo], TOMLType]
    ) -> Self:
        return cls(
            label=" | ".join(
                toml_type_factory(typ).label
                for typ in type_info.origin_types
                if typ is not NoneType
            ),
            renderer=lambda value: toml_type_factory(type(value)).render_value(value),
        )

    renderer: Callable[[Any], str]

    def render_value(self, value: Any) -> str:
        return self.renderer(value)


class RawTypenameError(ValueError):
    def __init__(self, type_: type) -> None:
        super().__init__(
            os.linesep.join(
                (
                    f"Raw data type names are not allowed and {type_} has no " "configured name.",
                    f"Use @{documented_dataclass.__module__}.documented_dataclass(alias=...) "
                    "to define one.",
                )
            )
        )


class MissingDocError(ValueError):
    def __init__(self, type_: type, field: FieldInfo | None = None) -> None:
        if field:
            error = os.linesep.join(
                (
                    f"Missing doc is not allowed and the field {field.name!r} in {type_} "
                    f"has none.",
                    f"Use dataclasses.field(metadata=science.dataclass.reflect.metadata(...)) to "
                    "add doc for the field.",
                )
            )
        else:
            error = f"Missing doc is not allowed and {type_} has no docstring."
        super().__init__(error)


class TOMLTypeRenderer(MarkdownParser):
    OPTION_SPEC = FrozenDict(
        {
            "allow_raw_typenames": bool_option(default=True),
            "allow_missing_doc": bool_option(default=True),
            "link_tables": bool_option(),
            "recurse_tables": bool_option(),
        }
    )

    @staticmethod
    def create_options(
        allow_raw_typenames: bool | None = None,
        allow_missing_doc: bool | None = None,
        link_tables: bool | None = None,
        recurse_tables: bool | None = None,
    ) -> Mapping[str, Any]:
        return {
            key: val
            for key, val in dict(
                allow_raw_typenames=allow_raw_typenames,
                allow_missing_doc=allow_missing_doc,
                link_tables=link_tables,
                recurse_tables=recurse_tables,
            ).items()
            if val is not None
        }

    @classmethod
    def default_options(
        cls,
        allow_raw_typenames: bool = True,
        allow_missing_doc: bool = True,
        link_tables: bool = False,
        recurse_tables: bool = False,
    ) -> Mapping[str, Any]:
        return cls.create_options(
            allow_raw_typenames=allow_raw_typenames,
            allow_missing_doc=allow_missing_doc,
            link_tables=link_tables,
            recurse_tables=recurse_tables,
        )

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> Self:
        options = cls.default_options(**options)
        return cls(
            allow_raw_typenames=options["allow_raw_typenames"],
            allow_missing_doc=options["allow_missing_doc"],
            link_tables=options["link_tables"],
            recurse_tables=options["recurse_tables"],
        )

    def __init__(
        self,
        allow_raw_typenames: bool,
        allow_missing_doc: bool,
        link_tables: bool,
        recurse_tables: bool,
    ) -> None:
        self._allow_raw_typenames = allow_raw_typenames
        self._allow_missing_doc = allow_missing_doc
        self._link_tables = link_tables
        self._recurse_tables = recurse_tables
        self._rendered_types = set[type]()

    def _extract_data_type_name(
        self, data_type: type[Dataclass] | DataclassInfo, *fallback_names: str
    ) -> str:
        class_info = (
            data_type if isinstance(data_type, DataclassInfo) else dataclass_info(data_type)
        )
        for name in class_info.alias, *fallback_names:
            if name:
                return name
        if self._allow_raw_typenames:
            return class_info.type.__name__

        raise RawTypenameError(class_info.type)

    def render_field(self, field: FieldInfo, owner: type[Dataclass]) -> Iterator[nodes.Node]:
        toml_type = self.as_toml_type(field.type, name=field.name, reference=field.reference)
        yield from self.parse_markdown(f"*type: {toml_type.label}*")
        if (
            field.has_default
            and field.default is not None
            and (field.default or field.type.issubtype(bool, str, int, float))
        ):
            yield from self.parse_markdown(
                f"*default*: **`{toml_type.render_value(field.default)}`**"
            )

        if field.doc:
            yield from self.parse_markdown(field.doc)
        elif not self._allow_missing_doc:
            raise MissingDocError(owner, field)

    def render_dataclass(self, data_type: type[Dataclass]) -> Iterator[nodes.Node]:
        if data_type in self._rendered_types:
            return

        if self._rendered_types:
            yield nodes.transition()

        self._rendered_types.add(data_type)

        class_info = dataclass_info(data_type)
        alias = self._extract_data_type_name(class_info)
        dataclass_section = Section.create(title=alias)
        if class_info.doc:
            dataclass_section.extend(self.parse_markdown(class_info.doc))
        elif not self._allow_missing_doc:
            raise MissingDocError(class_info.type)
        yield dataclass_section.node

        fields = deque(class_info.field_info)
        while fields:
            field = fields.popleft()
            if field.hidden:
                continue

            if field.inline:
                field_dataclass_type = field.type.dataclass
                if not field_dataclass_type:
                    raise TypeError(
                        f"Can only inline fields of @dataclass type. Asked to inline {field}."
                    )
                fields.extendleft(dataclass_info(field_dataclass_type).field_info)
                continue

            field_section = dataclass_section.create_subsection(title=field.name, name=field.name)
            field_section.extend(self.render_field(field, owner=class_info.type))

            if self._recurse_tables:
                for field_type in field.type.origin_types:
                    if dataclasses.is_dataclass(field_type):
                        yield from self.render_dataclass(field_type)
                if field.type.has_item_type and dataclasses.is_dataclass(field.type.item_type):
                    yield from self.render_dataclass(field.type.item_type)

    def as_toml_type(
        self, type_: type | TypeInfo, *, name: str | None = None, reference: bool = False
    ) -> TOMLType:
        type_info = type_ if isinstance(type_, TypeInfo) else TypeInfo(type_)

        def toml_type():
            if type_info.issubtype(Enum):
                return ChoiceType.for_enum(
                    type_info.origin_type, toml_type_factory=self.as_toml_type
                )

            if data_type := type_info.dataclass:
                if reference:
                    return self.as_toml_type(str)

                label = self._extract_data_type_name(data_type, name, "")
                if self._link_tables:
                    alias = label or data_type.__name__
                    link = f"[`{alias}`](#{directives.type_id(data_type)})"
                    label = link if label else f"`Table`: {link}"
                elif not label:
                    label = f"`Table[{data_type.__name__}]`"
                return TableType(label)

            if type_info.issubtype(Mapping):
                key_type, value_type = type_info.iter_parameter_types()
                assert key_type.issubtype(str)
                return TableType.create(self.as_toml_type(str if reference else value_type))

            if type_info.issubtype(Collection) and not type_info.issubtype(str):
                return ArrayType.create(
                    self.as_toml_type(str if reference else type_info.item_type)
                )

            if not type_info.has_origin_type:
                return UnionType.for_type_info(type_info, toml_type_factory=self.as_toml_type)

            if type_info.issubtype(str):
                return PrimitiveType("String")
            if type_info.issubtype(bool):
                return PrimitiveType("Boolean")
            if type_info.issubtype(int):
                return PrimitiveType("Integer")
            if type_info.issubtype(float):
                return PrimitiveType("Float")
            if type_info.type_ is Any:
                return PrimitiveType("Any")

            if reference:
                return self.as_toml_type(str)

            if self._allow_raw_typenames:
                return TOMLType(f"{type_info}")

            raise RawTypenameError(type_info.type_)

        classified_type = toml_type()
        if not type_info.optional:
            return classified_type
        return dataclasses.replace(toml_type(), label=f"{classified_type.label} (Optional)")

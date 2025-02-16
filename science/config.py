# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import difflib
import tomllib
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from io import BytesIO
from pathlib import Path
from textwrap import dedent
from typing import BinaryIO, Generic, TypeVar

from science.build_info import BuildInfo
from science.data import Accessor, Data
from science.dataclass import Dataclass
from science.dataclass.deserializer import HeterogeneousParser
from science.dataclass.deserializer import parse as parse_dataclass
from science.dataclass.reflect import FieldInfo, dataclass_info
from science.doc import DOC_SITE_URL
from science.errors import InputError
from science.frozendict import FrozenDict
from science.hashing import Digest, Provenance
from science.model import (
    Application,
    Identifier,
    Interpreter,
    InterpreterGroup,
    Provider,
)
from science.platform import LibC, Platform, PlatformSpec
from science.providers import get_provider


def parse_config(content: BinaryIO, source: str) -> Application:
    hashed_content = Digest.hasher(content)
    data = FrozenDict(tomllib.load(hashed_content))
    provenance = Provenance(source, digest=hashed_content.digest())
    return parse_config_data(Data(provenance=provenance, data=data))


def parse_config_file(path: Path) -> Application:
    with path.open(mode="rb") as fp:
        return parse_config(fp, source=fp.name)


def parse_config_str(config: str) -> Application:
    return parse_config(BytesIO(config.encode()), source="<string>")


def parse_build_info(data: Data) -> BuildInfo:
    return BuildInfo.gather(
        lift_toml=data.provenance, app_info=data.get_data("app_info", default={}, used=True).data
    )


def parse_platform_spec(data: Data | str) -> PlatformSpec:
    if isinstance(data, str):
        return PlatformSpec(Platform.parse(data))

    libc_value = data.get_str("libc", default="")
    libc = LibC(libc_value) if libc_value else None
    return PlatformSpec(platform=Platform.parse(data.get_str("platform")), libc=libc)


@dataclass(frozen=True)
class ProviderFields(Dataclass):
    id: Identifier
    provider: str
    lazy: bool = False


def parse_provider(data: Data) -> Provider:
    fields = parse_dataclass(data, ProviderFields)
    if not (provider_info := get_provider(fields.provider)):
        raise InputError(f"The provider '{fields.provider}' is not registered.")
    provider_type = provider_info.type
    config = parse_dataclass(data, provider_type.config_dataclass())
    return provider_type.create(identifier=fields.id, lazy=fields.lazy, config=config)


@dataclass(frozen=True)
class InterpreterGroupFields(Dataclass):
    id: Identifier
    selector: str
    members: tuple[str, ...]


def _iter_field_info(datatype: type[Dataclass]) -> Iterator[FieldInfo]:
    for field_info in dataclass_info(datatype).field_info:
        if not field_info.hidden and not field_info.inline:
            yield field_info
        elif field_info.inline and (dt := field_info.type.dataclass):
            yield from _iter_field_info(dt)


_D = TypeVar("_D", bound=Dataclass)


@dataclass(frozen=True)
class ValidConfig(Generic[_D]):
    @classmethod
    @cache
    def gather(cls, datatype: type[_D]) -> ValidConfig:
        return cls(
            datatype=datatype,
            fields=FrozenDict(
                {field_info.name: field_info for field_info in _iter_field_info(datatype)}
            ),
        )

    datatype: type[_D]
    fields: FrozenDict[str, FieldInfo]

    def access(self, field_name: str) -> ValidConfig | None:
        field_info = self.fields.get(field_name)
        if not field_info:
            return None

        if datatype := field_info.type.dataclass:
            return ValidConfig.gather(datatype)

        if field_info.type.has_item_type and dataclasses.is_dataclass(
            item_type := field_info.type.item_type
        ):
            return ValidConfig.gather(item_type)

        return None


def gather_unrecognized_application_config(
    lift: Data, index_start: int
) -> Mapping[Accessor, ValidConfig | None]:
    valid_config_by_unused_accessor: dict[Accessor, ValidConfig | None] = {}
    for unused_accessor, _ in lift.iter_unused_items(index_start=index_start):
        valid_config: ValidConfig | None = ValidConfig.gather(Application)
        for accessor in unused_accessor.iter_lineage():
            if not valid_config:
                break
            valid_config = valid_config.access(accessor.key)
        valid_config_by_unused_accessor[unused_accessor] = valid_config
    return valid_config_by_unused_accessor


def parse_config_data(data: Data) -> Application:
    lift = data.get_data("lift")

    interpreters_by_id = {
        (
            interp := parse_dataclass(
                interpreter, Interpreter, custom_parsers={Provider: parse_provider}
            )
        ).id: interp
        for interpreter in lift.get_data_list("interpreters", default=[])
    }

    def parse_interpreter_group(ig_data: Data) -> InterpreterGroup:
        fields = parse_dataclass(ig_data, InterpreterGroupFields)
        members = fields.members
        if len(members) < 2:
            raise InputError(
                f"At least two interpreter group members are needed to form an interpreter group. "
                f"Given {f"just {next(iter(members))!r}" if members else "none"} for interpreter "
                f"group {fields.id}."
            )
        return InterpreterGroup.create(
            id_=fields.id,
            selector=fields.selector,
            interpreters=[interpreters_by_id[Identifier(member)] for member in members],
        )

    application = parse_dataclass(
        lift,
        Application,
        interpreters=tuple(interpreters_by_id.values()),
        custom_parsers={
            BuildInfo: parse_build_info,
            InterpreterGroup: parse_interpreter_group,
            PlatformSpec: HeterogeneousParser.wrap(
                parse_platform_spec, Data, str, output_type=PlatformSpec
            ),
        },
    )

    unrecognized_config = gather_unrecognized_application_config(lift, index_start=1)
    if unrecognized_config:
        unrecognized_field_info = defaultdict[str, list[str]](list)
        index_used = False
        for accessor, valid_config in unrecognized_config.items():
            index_used |= accessor.path_includes_index()
            suggestions = unrecognized_field_info[accessor.render()]
            if valid_config:
                suggestions.extend(difflib.get_close_matches(accessor.key, valid_config.fields))

        field_column_width = max(map(len, unrecognized_field_info))
        unrecognized_fields = []
        for name, suggestions in unrecognized_field_info.items():
            line = name.rjust(field_column_width)
            if suggestions:
                line += f": Did you mean {' or '.join(suggestions)}?"
            unrecognized_fields.append(line)

        raise InputError(
            dedent(
                """\
                The following `lift` manifest entries in {manifest_source} were not recognized{index_parenthetical}:
                {unrecognized_fields}

                Refer to the lift manifest format specification at {doc_url} or by running `science doc open manifest`.
                """
            )
            .format(
                manifest_source=data.provenance.source,
                index_parenthetical=" (indexes are 1-based)" if index_used else "",
                unrecognized_fields="\n".join(unrecognized_fields),
                doc_url=f"{DOC_SITE_URL}/manifest.html",
            )
            .strip()
        )

    return application

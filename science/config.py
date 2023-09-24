# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import tomllib
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from textwrap import dedent
from typing import BinaryIO

from science.build_info import BuildInfo
from science.context import DocConfig, active_context_config
from science.data import Data
from science.dataclass import Dataclass
from science.dataclass.deserializer import parse as parse_dataclass
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


def parse_config_data(data: Data) -> Application:
    lift = data.get_data("lift")

    interpreters_by_id = OrderedDict(
        (
            (
                interp := parse_dataclass(
                    interpreter, Interpreter, custom_parsers={Provider: parse_provider}
                )
            ).id,
            interp,
        )
        for interpreter in lift.get_data_list("interpreters", default=[])
    )

    def parse_interpreter_group(ig_data: Data) -> InterpreterGroup:
        fields = parse_dataclass(ig_data, InterpreterGroupFields)
        members = fields.members
        if len(members) < 2:
            raise InputError(
                f"At least two interpreter group members are needed to form an interpreter group. "
                f"Given {f'just {next(iter(members))!r}' if members else 'none'} for interpreter "
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
        custom_parsers={BuildInfo: parse_build_info, InterpreterGroup: parse_interpreter_group},
    )

    unused_items = list(lift.iter_unused_items())
    if unused_items:
        doc_config = active_context_config(DocConfig)
        doc_url = (
            f"{doc_config.site}/manifest.html"
            if doc_config
            else "https://science.scie.app/manifest.html"
        )
        raise InputError(
            dedent(
                """\
                The following `lift` manifest entries in {manifest_source} were not recognized:
                {unrecognized_fields}

                Refer to the lift manifest format specification at {doc_url} or by running `science doc open manifest`.
                """
            )
            .format(
                manifest_source=data.provenance.source,
                unrecognized_fields="\n".join(key for key, _ in unused_items),
                doc_url=doc_url,
            )
            .strip()
        )

    return application

# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os

# This `no-infer-dep` will not be needed once we upgrade t0 a version of Pants that fixes:
#  https://github.com/pantsbuild/pants/issues/18055
import tomllib  # pants: no-infer-dep
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from packaging import version
from packaging.version import Version

from science.frozendict import FrozenDict
from science.model import (
    Application,
    Binding,
    Command,
    Digest,
    Env,
    File,
    FileSource,
    FileType,
    Identifier,
    Interpreter,
    InterpreterGroup,
    Ptex,
    ScieJump,
)
from science.platform import Platform
from science.providers import get_provider


def parse_config(content: BinaryIO) -> Application:
    return parse_config_data(tomllib.load(content))


def parse_config_file(path: Path) -> Application:
    with path.open(mode="rb") as fp:
        return parse_config(fp)


def parse_config_str(config: str) -> Application:
    return parse_config(BytesIO(config.encode()))


def parse_command(data: Mapping[str, Any]) -> Command:
    env = Env()
    if env_data := data.get("env"):
        remove_exact = frozenset[str](env_data.get("remove", ()))
        remove_re = frozenset[str](env_data.get("remove_re", ()))
        replace = FrozenDict[str, str](env_data.get("replace", {}))
        default = FrozenDict[str, str](env_data.get("default", {}))
        env = Env(default=default, replace=replace, remove_exact=remove_exact, remove_re=remove_re)

    return Command(
        name=data.get("name") or None,  # N.B.: Normalizes "" to None
        description=data.get("description"),
        exe=data["exe"],
        args=tuple(data.get("args", ())),
        env=env,
    )


def parse_version_field(data: Mapping[str, Any]) -> Version | None:
    return version.parse(version_str) if (version_str := data.get("version")) else None


def parse_digest_field(data: Mapping[str, Any]) -> Digest | None:
    return (
        Digest(size=digest_data["size"], fingerprint=digest_data["fingerprint"])
        if (digest_data := data.get("digest"))
        else None
    )


def parse_config_data(data: Mapping[str, Any]) -> Application:
    # TODO(John Sirois): wrap up [] accesses to provide useful information on KeyError.

    science = data["science"]
    application_name = science["name"]
    description = science.get("description")
    load_dotenv = science.get("load_dotenv", False)

    platforms = frozenset(
        Platform.parse(platform) for platform in science.get("platforms", ["current"])
    )
    if not platforms:
        raise ValueError(
            "There must be at least one platform defined for a science application. Leave "
            "un-configured to request just the current platform."
        )

    scie_jump = (
        ScieJump(
            version=parse_version_field(scie_jump_table), digest=parse_digest_field(scie_jump_table)
        )
        if (scie_jump_table := science.get("scie-jump"))
        else ScieJump()
    )

    ptex = (
        Ptex(
            id=Identifier.parse(ptex_table.get("id", "ptex")),
            argv1=ptex_table.get("lazy_argv1", "{scie.lift}"),
            version=parse_version_field(ptex_table),
            digest=parse_digest_field(ptex_table),
        )
        if (ptex_table := science.get("ptex"))
        else None
    )

    interpreters_by_id = OrderedDict[str, Interpreter]()
    for interpreter in science.get("interpreters", ()):
        identifier = Identifier.parse(interpreter.pop("id"))
        lazy = interpreter.pop("lazy", False)
        provider_name = interpreter.pop("provider")
        if not (provider := get_provider(provider_name)):
            raise ValueError(f"The provider '{provider_name}' is not registered.")
        interpreters_by_id[identifier.value] = Interpreter(
            id=identifier,
            provider=provider.create(identifier=identifier, lazy=lazy, **interpreter),
            lazy=lazy,
        )

    interpreter_groups = []
    for interpreter_group in science.get("interpreter_groups", ()):
        identifier = Identifier.parse(interpreter_group.pop("id"))
        selector = interpreter_group.pop("selector")
        members = interpreter_group.pop("members")
        if len(members) < 2:
            raise ValueError(
                f"At least two interpreter group members are needed to form an interpreter group. "
                f"Given {f'just {next(iter(members))!r}' if members else 'none'} for interpreter "
                f"group {identifier}."
            )
        interpreter_groups.append(
            InterpreterGroup.create(
                id_=identifier,
                selector=selector,
                interpreters=[interpreters_by_id[member] for member in members],
            )
        )

    if interpreter_groups and scie_jump.version and scie_jump.version < Version("0.11.0"):
        raise ValueError(
            f"Cannot use scie-jump {scie_jump.version}.{os.linesep}"
            f"This configuration uses interpreter groups and these require scie-jump v0.11.0 or "
            f"greater."
        )

    files = []
    for file in science.get("files", ()):
        file_name = file["name"]
        digest = parse_digest_field(file)
        file_type = FileType(file_type_name) if (file_type_name := file.get("type")) else None

        source: FileSource = None
        if source_name := file.get("source"):
            match source_name:
                case "fetch":
                    source = "fetch"
                case file_name:
                    source = Binding(file_name)

        files.append(
            File(
                name=file_name,
                key=file.get("key"),
                digest=digest,
                type=file_type,
                is_executable=file.get("executable", False),
                eager_extract=file.get("eager_extract", False),
                source=source,
            )
        )

    commands = [parse_command(command) for command in science["commands"]]
    if not commands:
        raise ValueError("There must be at least one command defined in a science application.")

    bindings = [parse_command(command) for command in science.get("bindings", ())]

    return Application(
        name=application_name,
        description=description,
        load_dotenv=load_dotenv,
        platforms=platforms,
        scie_jump=scie_jump,
        ptex=ptex,
        interpreters=tuple(interpreters_by_id.values()),
        interpreter_groups=tuple(interpreter_groups),
        files=tuple(files),
        commands=frozenset(commands),
        bindings=frozenset(bindings),
    )

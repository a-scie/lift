# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

# This `no-infer-dep` will not be needed once we upgrade ti a version of Pants that fixes:
#  https://github.com/pantsbuild/pants/issues/18055
import tomllib  # pants: no-infer-dep
from pathlib import Path
from typing import Any, Mapping

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
)
from science.platform import Platform
from science.provider import get_provider


def parse_config_file(path: Path) -> Application:
    with path.open(mode="rb") as fp:
        return parse_config_data(tomllib.load(fp))


def parse_config_str(config: str) -> Application:
    return parse_config_data(tomllib.loads(config))


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

    interpreters = []
    for interpreter in science.get("interpreters", ()):
        identifier = Identifier.parse(interpreter["id"])
        lazy = interpreter.get("lazy", False)
        provider_name = interpreter["provider"]
        if not (provider := get_provider(provider_name)):
            raise ValueError(f"The provider '{provider_name}' is not registered.")
        interpreters.append(
            Interpreter(
                id=identifier,
                provider=provider.create(
                    identifier=identifier, lazy=lazy, **interpreter.get("configuration", {})
                ),
                lazy=lazy,
            )
        )

    files = []
    for file in science.get("files", ()):
        file_name = file["name"]
        digest = (
            Digest(size=digest_data["size"], fingerprint=digest_data["fingerprint"])
            if (digest_data := file.get("digest"))
            else None
        )
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
        interpreters=tuple(interpreters),
        files=tuple(files),
        commands=frozenset(commands),
        bindings=frozenset(bindings),
    )

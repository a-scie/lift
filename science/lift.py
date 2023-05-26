# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, TextIO

from science.build_info import BuildInfo
from science.model import (
    Binding,
    Command,
    Distribution,
    Fetch,
    File,
    InterpreterGroup,
    ScieJump,
)
from science.platform import Platform


def _render_file(file: File) -> dict[str, Any]:
    data: dict[str, Any] = {"name": file.name}
    if key := file.key:
        data["key"] = key
    if digest := file.digest:
        data.update(dict(size=digest.size, hash=digest.fingerprint))
    if file_type := file.type:
        data["type"] = file_type.value
    if file.is_executable:
        data["executable"] = True
    if file.eager_extract:
        data["eager_extract"] = True
    match file.source:
        case Fetch(lazy=True) as fetch:
            data["source"] = fetch.binding_name
        case Binding(name):
            data["source"] = name
    return data


def _render_command(
    command: Command,
    platform: Platform,
    distributions: Iterable[Distribution],
    interpreter_groups: Iterable[InterpreterGroup],
) -> tuple[str, dict[str, Any]]:
    env: dict[str, str | None] = {}

    def expand_placeholders(text: str) -> str:
        for distribution in distributions:
            text = distribution.expand_placeholders(text)
        for interpreter_group in interpreter_groups:
            text, ig_env = interpreter_group.expand_placeholders(platform, text)
            env.update(ig_env)
        return text

    cmd: dict[str, Any] = {"exe": expand_placeholders(command.exe)}

    args = [expand_placeholders(arg) for arg in command.args]
    if args:
        cmd["args"] = args

    for name, value in command.env.default.items():
        env[name] = expand_placeholders(value)
    for name, value in command.env.replace.items():
        env[f"={name}"] = expand_placeholders(value)
    for name in command.env.remove_exact:
        env[f"={name}"] = None
    for re in command.env.remove_re:
        env[re] = None
    if env:
        cmd["env"] = env

    return command.name or "", cmd


def emit_manifest(
    output: TextIO,
    name: str,
    description: str | None,
    load_dotenv: bool,
    scie_jump: ScieJump,
    platform: Platform,
    distributions: Iterable[Distribution],
    interpreter_groups: Iterable[InterpreterGroup],
    files: Iterable[File],
    commands: Iterable[Command],
    bindings: Iterable[Command],
    fetch_urls: dict[str, str],
    build_info: BuildInfo | None = None,
    app_info: Mapping[str, Any] | None = None,
) -> None:
    def render_files() -> list[dict[str, Any]]:
        return [_render_file(file) for file in files]

    def render_commands(cmds: Iterable[Command]) -> dict[str, dict[str, Any]]:
        return dict(
            _render_command(cmd, platform, distributions, interpreter_groups) for cmd in cmds
        )

    scie_data = {
        "lift": {
            "name": name,
            "description": description,
            "load_dotenv": load_dotenv,
            "files": render_files(),
            "boot": {
                "commands": render_commands(commands),
                "bindings": render_commands(bindings),
            },
        }
    }
    data = dict[str, Any](scie=scie_data)
    if build_info:
        data.update(science=build_info.to_dict(**(app_info or {})))
    if fetch_urls:
        data.update(ptex=fetch_urls)

    scie_jump_data = dict[str, Any]()
    if (scie_jump_version := scie_jump.version) and (scie_jump_digest := scie_jump.digest):
        scie_jump_data.update(version=str(scie_jump_version), size=scie_jump_digest.size)
    if scie_jump_data:
        scie_data.update(jump=scie_jump_data)

    json.dump(data, output, indent=2, sort_keys=True)

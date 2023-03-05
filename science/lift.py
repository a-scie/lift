# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import json
from typing import Any, Iterable, TextIO

from science.model import Binding, Command, Distribution, File


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
        case ("fetch" as name) | Binding(name):
            data["source"] = name
    return data


def _render_command(
    command: Command, distributions: Iterable[Distribution]
) -> tuple[str, dict[str, Any]]:
    exe = command.exe
    for distribution in distributions:
        exe = distribution.expand_placeholders(exe)
    cmd: dict[str, Any] = {"exe": exe}

    args = []
    for arg in command.args:
        for distribution in distributions:
            arg = distribution.expand_placeholders(arg)
        args.append(arg)
    if args:
        cmd["args"] = args

    env: dict[str, str | None] = {}
    for name, value in command.env.default.items():
        for distribution in distributions:
            value = distribution.expand_placeholders(value)
        env[name] = value
    for name, value in command.env.replace.items():
        for distribution in distributions:
            value = distribution.expand_placeholders(value)
        env[f"={name}"] = value
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
    distributions: Iterable[Distribution],
    files: Iterable[File],
    commands: Iterable[Command],
    bindings: Iterable[Command],
    fetch_urls: dict[str, str],
) -> None:
    lift = {
        "name": name,
        "description": description,
        "load_dotenv": load_dotenv,
        "files": [_render_file(file) for file in files],
        "boot": {
            "commands": dict(_render_command(command, distributions) for command in commands),
            "bindings": dict(_render_command(command, distributions) for command in bindings),
        },
    }

    data: dict[str, Any] = {"scie": {"lift": lift}}
    if fetch_urls:
        data["ptex"] = fetch_urls

    json.dump(data, output, indent=2, sort_keys=True)

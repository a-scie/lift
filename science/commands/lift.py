# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, TextIO

from science import a_scie
from science.build_info import BuildInfo
from science.errors import InputError
from science.fetcher import fetch_and_verify
from science.model import (
    Application,
    Binding,
    Command,
    Distribution,
    Fetch,
    File,
    FileType,
    InterpreterGroup,
    ScieJump,
)
from science.platform import Platform


@dataclass(frozen=True)
class AppInfo:
    @classmethod
    def assemble(cls, app_infos: Iterable[AppInfo]) -> Mapping[str, Any]:
        return {app_info.key: app_info.value for app_info in app_infos}

    @classmethod
    def parse(cls, value: str) -> AppInfo:
        components = value.split("=", 1)
        if len(components) != 2:
            raise InputError(
                f"Invalid app info. An app info entry must be of the form `<key>=<value>`: {value}"
            )
        return cls(key=components[0], value=components[1])

    key: str
    value: str


@dataclass(frozen=True)
class FileMapping:
    @classmethod
    def parse(cls, value: str) -> FileMapping:
        components = value.split("=", 1)
        if len(components) != 2:
            raise InputError(
                "Invalid file mapping. A file mapping must be of the form "
                f"`(<name>|<key>)=<path>`: {value}"
            )
        return cls(id=components[0], path=Path(components[1]))

    id: str
    path: Path


@dataclass(frozen=True)
class PlatformInfo:
    @classmethod
    def create(cls, application: Application, use_suffix: bool = False) -> PlatformInfo:
        current = Platform.current()
        use_suffix = use_suffix or application.platforms != frozenset([current])
        return cls(current=current, use_suffix=use_suffix)

    current: Platform
    use_suffix: bool

    def binary_name(self, name: str, target_platform: Platform) -> str:
        return (
            target_platform.qualified_binary_name(name)
            if self.use_suffix
            else target_platform.binary_name(name)
        )


@dataclass(frozen=True)
class LiftConfig:
    file_mappings: tuple[FileMapping, ...] = ()
    invert_lazy_ids: frozenset[str] = frozenset()
    include_provenance: bool = False
    app_info: tuple[AppInfo, ...] = ()
    app_name: str | None = None


def export_manifest(
    lift_config: LiftConfig,
    application: Application,
    dest_dir: Path,
    *,
    platforms: Iterable[Platform] | None = None,
) -> Iterator[tuple[Platform, Path]]:
    app_info = AppInfo.assemble(lift_config.app_info)

    for platform in platforms or application.platforms:
        chroot = dest_dir / platform.value
        chroot.mkdir(parents=True, exist_ok=True)

        bindings = list[Command]()
        distributions = list[Distribution]()

        requested_files = deque[File]()
        file_paths_by_id = {
            file_mapping.id: file_mapping.path.resolve()
            for file_mapping in lift_config.file_mappings
        }
        inverted = list[str]()

        def maybe_invert_lazy(file: File) -> File:
            if file.id in lift_config.invert_lazy_ids:
                match file.source:
                    case Fetch(_, lazy=lazy) as fetch:
                        inverted.append(file.id)
                        return dataclasses.replace(
                            file, source=dataclasses.replace(fetch, lazy=not lazy)
                        )
                    case Binding(name):
                        raise InputError(f"Cannot make binding {name!r} non-lazy.")
                    case None:
                        raise InputError(f"Cannot lazy fetch local file {file.name!r}.")
            return file

        for interpreter in application.interpreters:
            distribution = interpreter.provider.distribution(platform)
            if distribution:
                distributions.append(distribution)
                requested_files.append(maybe_invert_lazy(distribution.file))
        requested_files.extend(map(maybe_invert_lazy, application.files))
        if (actually_inverted := frozenset(inverted)) != lift_config.invert_lazy_ids:
            raise InputError(
                "There following files were not present to invert laziness for: "
                f"{', '.join(sorted(lift_config.invert_lazy_ids - actually_inverted))}"
            )

        if any(isinstance(file.source, Fetch) and file.source.lazy for file in requested_files):
            ptex = a_scie.ptex(chroot, specification=application.ptex, platform=platform)
            file_paths_by_id[ptex.id] = chroot / ptex.name
            requested_files.appendleft(ptex)
            argv1 = (
                application.ptex.argv1
                if application.ptex and application.ptex.argv1
                else "{scie.lift}"
            )
            bindings.append(Fetch.create_binding(fetch_exe=ptex, argv1=argv1))
        bindings.extend(application.bindings)

        files = list[File]()
        fetch_urls = dict[str, str]()
        for requested_file in requested_files:
            file = requested_file
            file_path: Path | None = None
            match requested_file.source:
                case Fetch(url=url, lazy=True):
                    fetch_urls[requested_file.name] = url
                case Fetch(url=url, lazy=False):
                    file = dataclasses.replace(requested_file, source=None)
                    file_path = fetch_and_verify(
                        url,
                        fingerprint=requested_file.digest,
                        executable=requested_file.is_executable,
                    )
                case None:
                    file_path = (
                        file_paths_by_id.get(requested_file.id) or Path.cwd() / requested_file.name
                    )
                    if not file_path.exists():
                        raise InputError(
                            f"The file for {requested_file.id} is not mapped or cannot be found at "
                            f"{file_path.relative_to(Path.cwd())} relative to the cwd of "
                            f"{Path.cwd()}."
                        )
            files.append(file)

            target = chroot / requested_file.name
            if file_path and file_path.is_dir():
                if requested_file.type and requested_file.type is not FileType.Directory:
                    raise InputError(
                        f"The file for {requested_file.id} is expected to be a "
                        f"{requested_file.type} but maps to the directory {file_path}."
                    )

                # N.B.: The scie-jump boot pack expects a local directory to zip up as a sibling. It
                # then includes the local sibling <dir>.zip in the scie. If we point it at the
                # directory `file_path` directly via symlink it will follow the symlink and zip up
                # the directory as a sibling there instead and not find the resulting zip. As such
                # we create a thin local directory of symlinks here for it to work against.
                target.mkdir(parents=True, exist_ok=True)
                for entry in file_path.iterdir():
                    (target / entry.name).symlink_to(entry)
            elif file_path:
                requested_file.maybe_check_digest(file_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.symlink_to(file_path)

        lift_manifest = chroot / "lift.json"

        build_info = application.build_info if lift_config.include_provenance else None

        with open(lift_manifest, "w") as lift_manifest_output:
            _emit_manifest(
                lift_manifest_output,
                name=application.name,
                description=application.description,
                load_dotenv=application.load_dotenv,
                base=application.base,
                scie_jump=application.scie_jump or ScieJump(),
                platform=platform,
                distributions=distributions,
                interpreter_groups=application.interpreter_groups,
                files=requested_files,
                commands=application.commands,
                bindings=bindings,
                fetch_urls=fetch_urls,
                build_info=build_info,
                app_info=app_info,
            )
        yield platform, lift_manifest


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

    if command_env := command.env:
        for name, value in command_env.default.items():
            env[name] = expand_placeholders(value)
        for name, value in command_env.replace.items():
            env[f"={name}"] = expand_placeholders(value)
        for name in command_env.remove_exact:
            env[f"={name}"] = None
        for re in command_env.remove_re:
            env[re] = None
    if env:
        cmd["env"] = env

    if description := command.description:
        cmd["description"] = description

    return command.name or "", cmd


def _emit_manifest(
    output: TextIO,
    name: str,
    description: str | None,
    load_dotenv: bool,
    base: str | None,
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

    lift_data = {
        "name": name,
        "description": description,
        "load_dotenv": load_dotenv,
        "files": render_files(),
        "boot": {
            "commands": render_commands(commands),
            "bindings": render_commands(bindings),
        },
    }
    if base:
        lift_data.update(base=base)

    scie_data = {"lift": lift_data}
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

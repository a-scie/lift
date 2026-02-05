# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).


import atexit
import dataclasses
import json
import shutil
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, TextIO
from zipfile import ZipInfo

from science import a_scie, providers
from science.build_info import BuildInfo
from science.errors import InputError
from science.fetcher import fetch_and_verify
from science.fs import temporary_directory
from science.hashing import Digest
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
from science.platform import CURRENT_PLATFORM_SPEC, PlatformSpec


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
    def create(cls, application: Application, use_suffix: bool | None = None) -> PlatformInfo:
        return cls(
            use_suffix=(
                use_suffix
                if use_suffix is not None
                else application.platform_specs != frozenset([CURRENT_PLATFORM_SPEC])
            ),
        )

    use_suffix: bool

    def binary_name(self, name: str, target_platform: PlatformSpec) -> str:
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
    platform_specs: tuple[PlatformSpec, ...] = ()


def export_manifest(
    lift_config: LiftConfig,
    application: Application,
    dest_dir: Path,
    *,
    platform_specs: Iterable[PlatformSpec] | None = None,
    use_jump: Path | None = None,
    hydrate_files: bool = False,
) -> Iterator[tuple[PlatformSpec, Path, Path, ScieJump]]:
    app_info = AppInfo.assemble(lift_config.app_info)

    for platform_spec in platform_specs or application.platform_specs:
        chroot = dest_dir / platform_spec.value
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
                        # MyPy does not handle dataclass_transform yet: https://github.com/python/mypy/issues/14293
                        return dataclasses.replace(
                            file,
                            source=dataclasses.replace(fetch, lazy=not lazy),  # type: ignore[misc]
                        )  # type: ignore[misc]
                    case Binding(name):
                        raise InputError(f"Cannot make binding {name!r} non-lazy.")
                    case None:
                        raise InputError(f"Cannot lazy fetch local file {file.name!r}.")
            return file

        for interpreter in application.interpreters:
            distribution = interpreter.provider.distribution(platform_spec)
            if distribution is None:
                raise InputError(
                    f"No compatible {providers.name(interpreter.provider)} distribution was found "
                    f"for {platform_spec}."
                )
            if distribution:
                distributions.append(distribution)
                requested_files.append(maybe_invert_lazy(distribution.file))
        requested_files.extend(map(maybe_invert_lazy, application.files))
        if (actually_inverted := frozenset(inverted)) != lift_config.invert_lazy_ids:
            raise InputError(
                "There following files were not present to invert laziness for: "
                f"{', '.join(sorted(lift_config.invert_lazy_ids - actually_inverted))}"
            )

        fetches_present = any(
            isinstance(file.source, Fetch) and file.source.lazy for file in requested_files
        )
        if application.ptex or fetches_present:
            ptex = a_scie.ptex(specification=application.ptex, platform_spec=platform_spec)
            (chroot / ptex.binary_name).symlink_to(ptex.path)
            ptex_key = application.ptex.id if application.ptex and application.ptex.id else "ptex"
            ptex_file = File(
                name=ptex.binary_name,
                key=ptex_key,
                digest=ptex.digest,
                type=FileType.Blob,
                is_executable=True,
            )

            file_paths_by_id[ptex_file.id] = chroot / ptex_file.name
            requested_files.appendleft(ptex_file)
            if fetches_present:
                argv1 = (
                    application.ptex.argv1
                    if application.ptex and application.ptex.argv1
                    else "{scie.lift}"
                )
                bindings.append(Fetch.create_binding(fetch_exe=ptex_file, argv1=argv1))
        bindings.extend(application.bindings)

        if not requested_files:
            empty_scie_tote = File(name="empty-scie-tote")
            with temporary_directory(empty_scie_tote.name, delete=False) as td:
                empty_zip = td / "empty.zip"
                zipfile.ZipFile(empty_zip, "w").close()
            atexit.register(shutil.rmtree, td, ignore_errors=True)
            file_paths_by_id[empty_scie_tote.id] = empty_zip
            requested_files.append(empty_scie_tote)

        files = list[File]()
        fetch_urls = dict[str, str]()
        for requested_file in requested_files:
            file = requested_file
            file_path: Path | None = None
            match requested_file.source:
                case Fetch(url=url, lazy=True):
                    fetch_urls[requested_file.name] = url
                case Fetch(url=url, lazy=False):
                    # MyPy does not handle dataclass_transform yet: https://github.com/python/mypy/issues/14293
                    file = dataclasses.replace(requested_file, source=None)  # type: ignore[misc]
                    file_path = fetch_and_verify(
                        url,
                        fingerprint=requested_file.digest,
                        executable=requested_file.is_executable,
                    ).path
                case None:
                    file_path = (
                        file_paths_by_id.get(requested_file.id) or Path.cwd() / requested_file.name
                    )
                    if not file_path.exists():
                        if file_path.is_relative_to(Path.cwd()):
                            raise InputError(
                                f"The file for {requested_file.id} is not mapped or cannot be "
                                f"found at {file_path.relative_to(Path.cwd())} relative to the cwd "
                                f"of {Path.cwd()}."
                            )
                        raise InputError(
                            f"The file for {requested_file.id} is not mapped or cannot be found at "
                            f"{file_path}."
                        )

            if file_path and not file.type:
                if file_path.is_dir():
                    file_type = FileType.Directory
                elif extension := file_path.suffixes:
                    try:
                        file_type = FileType.for_extension("".join(extension))
                    except InputError:
                        file_type = FileType.Blob
                else:
                    file_type = FileType.Blob
                if file_type:
                    file = dataclasses.replace(file, type=file_type)

            if hydrate_files and file_path and file.type is FileType.Directory:
                zip_path = dest_dir / f"{file.name}.zip"
                with zipfile.ZipFile(zip_path, "w") as zip_fp:
                    for root, dir_names, file_names in file_path.walk():
                        for rel_path in sorted(dir_names + file_names):
                            src_path = root / rel_path
                            arc_name = "/".join(src_path.relative_to(file_path).parts)
                            zip_info = ZipInfo.from_file(src_path, arc_name)
                            zip_info.date_time = 1980, 1, 1, 0, 0, 0
                            if zip_info.is_dir():
                                # See: https://github.com/python/cpython/issues/119052
                                zip_info.CRC = 0
                                zip_fp.mkdir(zip_info)
                            else:
                                with (
                                    src_path.open("rb") as src_fp,
                                    zip_fp.open(zip_info, "w") as dst_fp,
                                ):
                                    shutil.copyfileobj(src_fp, dst_fp)
                file_path = Path(zip_path)
            if hydrate_files and file_path and not file.digest and not file_path.is_dir():
                file = dataclasses.replace(
                    file,
                    digest=Digest.hash(file_path),
                    zipped_directory=file.type is FileType.Directory,
                )
            files.append(file)

            target = chroot / (
                f"{file.name}.zip"
                if hydrate_files and file.type is FileType.Directory
                else file.name
            )
            if not hydrate_files and file_path and file_path.is_dir():
                if file.type and file.type is not FileType.Directory:
                    raise InputError(
                        f"The file for {file.id} is expected to be a {file.type} but maps to the "
                        f"directory {file_path}."
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
                file.maybe_check_digest(file_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.symlink_to(file_path)

        lift_manifest = chroot / "lift.json"

        build_info = application.build_info if lift_config.include_provenance else None

        load_result = (
            a_scie.custom_jump(repo_path=use_jump)
            if use_jump
            else a_scie.jump(specification=application.scie_jump, platform_spec=platform_spec)
        )
        if load_result.version:
            scie_jump = ScieJump(version=load_result.version, digest=load_result.digest)
        else:
            scie_jump = ScieJump()

        with open(lift_manifest, "w") as lift_manifest_output:
            _emit_manifest(
                lift_manifest_output,
                name=application.name,
                description=application.description,
                load_dotenv=application.load_dotenv,
                base=application.base,
                scie_jump=scie_jump,
                platform_spec=platform_spec,
                distributions=distributions,
                interpreter_groups=application.interpreter_groups,
                files=files,
                commands=application.commands,
                bindings=bindings,
                fetch_urls=fetch_urls,
                build_info=build_info,
                app_info=app_info,
            )
        yield platform_spec, lift_manifest, load_result.path, scie_jump


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
    platform_spec: PlatformSpec,
    distributions: Iterable[Distribution],
    interpreter_groups: Iterable[InterpreterGroup],
) -> tuple[str, dict[str, Any]]:
    env: dict[str, str | None] = {}

    def expand_placeholders(text: str) -> str:
        for distribution in distributions:
            text = distribution.expand_placeholders(platform_spec, text)
        for interpreter_group in interpreter_groups:
            text, ig_env = interpreter_group.expand_placeholders(platform_spec, text)
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
    platform_spec: PlatformSpec,
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
            _render_command(cmd, platform_spec, distributions, interpreter_groups) for cmd in cmds
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

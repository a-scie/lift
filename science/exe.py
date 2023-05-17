# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import functools
import hashlib
import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO, Iterable, Iterator, Mapping

import click
import click_log
from packaging import version

from science import __version__, a_scie, lift
from science.config import parse_config
from science.errors import InputError
from science.fetcher import fetch_and_verify
from science.model import Application, Binding, Command, Distribution, Fetch, File
from science.platform import Platform

logger = logging.getLogger(__name__)


def _log_fatal(
    type_: type[BaseException],
    value: BaseException,
    tb: TracebackType,
    *,
    always_include_backtrace: bool,
) -> None:
    if always_include_backtrace or not isinstance(value, InputError):
        click.secho("".join(traceback.format_tb(tb)), fg="yellow", file=sys.stderr, nl=False)
        click.secho(
            f"{type_.__module__}.{type_.__qualname__}: ", fg="yellow", file=sys.stderr, nl=False
        )
    click.secho(value, fg="red", file=sys.stderr)


@click.group(
    context_settings=dict(auto_envvar_prefix="SCIENCE", help_option_names=["-h", "--help"])
)
@click.version_option(__version__, "-V", "--version", message="%(version)s")
@click.option("-v", "--verbose", count=True)
@click.option("-q", "--quiet", count=True)
def _main(verbose: int, quiet: int) -> None:
    """Science helps you prepare scies for your application.

    Science provides a high-level configuration file format for a scie application and can build
    scies and export scie lift manifests from these configuration files.

    For more information on the configuration file format, see:
    https://github.com/a-scie/lift/blob/main/docs/manifest.md
    """
    verbosity = verbose - quiet
    sys.excepthook = functools.partial(_log_fatal, always_include_backtrace=verbosity > 0)
    root_logger = click_log.basic_config()
    match verbosity:
        case v if v <= -2:
            root_logger.setLevel(logging.FATAL)
        case -1:
            root_logger.setLevel(logging.ERROR)
        case 0:
            root_logger.setLevel(logging.WARNING)
        case 1:
            root_logger.setLevel(logging.INFO)
        case v if v >= 2:
            root_logger.setLevel(logging.DEBUG)


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


@contextmanager
def _temporary_directory(cleanup: bool) -> Iterator[Path]:
    if cleanup:
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)
    else:
        yield Path(tempfile.mkdtemp())


def _export(
    application: Application,
    file_mappings: list[FileMapping],
    dest_dir: Path,
    *,
    invert_lazy_ids: frozenset[str] = frozenset(),
    force: bool = False,
    platforms: Iterable[Platform] | None = None,
    include_provenance: bool = False,
    app_info: Mapping[str, Any] | None = None,
) -> Iterator[tuple[Platform, Path]]:
    for platform in platforms or application.platforms:
        chroot = dest_dir / platform.value
        if force:
            shutil.rmtree(chroot, ignore_errors=True)
        chroot.mkdir(parents=True, exist_ok=False)

        bindings: list[Command] = []
        distributions: list[Distribution] = []

        requested_files: list[File] = []
        file_paths_by_id = {
            file_mapping.id: file_mapping.path.resolve() for file_mapping in file_mappings
        }
        inverted = list[str]()

        def maybe_invert_lazy(file: File) -> File:
            if file.id in invert_lazy_ids:
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
        if (actually_inverted := frozenset(inverted)) != invert_lazy_ids:
            raise InputError(
                "There following files were not present to invert laziness for: "
                f"{', '.join(sorted(invert_lazy_ids - actually_inverted))}"
            )

        if any(isinstance(file.source, Fetch) and file.source.lazy for file in requested_files):
            ptex = a_scie.ptex(chroot, specification=application.ptex, platform=platform)
            file_paths_by_id[ptex.id] = chroot / ptex.name
            requested_files.append(ptex)
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
            if file_path:
                requested_file.maybe_check_digest(file_path)
                target = chroot / requested_file.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.symlink_to(file_path)

        lift_manifest = chroot / "lift.json"

        build_info = application.build_info if include_provenance else None

        with open(lift_manifest, "w") as lift_manifest_output:
            lift.emit_manifest(
                lift_manifest_output,
                name=application.name,
                description=application.description,
                load_dotenv=application.load_dotenv,
                scie_jump=application.scie_jump,
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


@_main.command()
@click.argument("config", type=click.File("rb"), default="lift.toml")
@click.option(
    "--file",
    "file_mappings",
    type=FileMapping.parse,
    multiple=True,
    default=[],
    envvar="SCIENCE_EXPORT_FILE",
)
@click.option(
    "--invert-lazy",
    "invert_lazy_ids",
    multiple=True,
    default=[],
    envvar="SCIENCE_EXPORT_INVERT_LAZY",
)
@click.option("--dest-dir", type=Path, default=Path.cwd())
@click.option("--force", is_flag=True)
@click.option("--include-provenance", is_flag=True)
@click.option("--name", "app_name")
@click.option(
    "--app-info",
    type=AppInfo.parse,
    multiple=True,
    default=[],
    envvar="SCIENCE_EXPORT_APP_INFO",
)
def export(
    config: BinaryIO,
    file_mappings: list[FileMapping],
    invert_lazy_ids: list[str],
    dest_dir: Path,
    force: bool,
    include_provenance: bool,
    app_name: str | None,
    app_info: list[AppInfo],
) -> None:
    """Export the application configuration as one or more scie lift manifests."""

    application = parse_config(config, source=config.name)
    if app_name:
        application = dataclasses.replace(application, name=app_name)

    for _, lift_manifest in _export(
        application,
        file_mappings,
        invert_lazy_ids=frozenset(invert_lazy_ids),
        dest_dir=dest_dir,
        force=force,
        include_provenance=include_provenance,
        app_info=AppInfo.assemble(app_info),
    ):
        click.echo(lift_manifest)


@_main.command()
@click.argument("config", type=click.File("rb"), default="lift.toml")
@click.option(
    "--file",
    "file_mappings",
    type=FileMapping.parse,
    multiple=True,
    default=[],
    envvar="SCIENCE_BUILD_FILE",
)
@click.option(
    "--invert-lazy",
    "invert_lazy_ids",
    multiple=True,
    default=[],
    envvar="SCIENCE_BUILD_INVERT_LAZY",
)
@click.option("--dest-dir", type=Path, default=Path.cwd())
@click.option("--preserve-sandbox", is_flag=True)
@click.option("--use-jump", type=Path)
@click.option("--include-provenance", is_flag=True)
@click.option("--name", "app_name")
@click.option(
    "--app-info",
    type=AppInfo.parse,
    multiple=True,
    default=[],
    envvar="SCIENCE_BUILD_APP_INFO",
)
@click.option(
    "--hash",
    "hash_functions",
    type=click.Choice(sorted(hashlib.algorithms_guaranteed)),
    multiple=True,
    default=[],
    envvar="SCIENCE_BUILD_HASH",
)
@click.option("--use-platform-suffix", is_flag=True)
def build(
    config: BinaryIO,
    file_mappings: list[FileMapping],
    invert_lazy_ids: list[str],
    dest_dir: Path,
    preserve_sandbox: bool,
    use_jump: Path | None,
    include_provenance: bool,
    app_name: str | None,
    app_info: list[AppInfo],
    hash_functions: list[str],
    use_platform_suffix: bool,
) -> None:
    """Build the application executable(s)."""

    application = parse_config(config, source=config.name)
    if app_name:
        application = dataclasses.replace(application, name=app_name)

    current_platform = Platform.current()
    platforms = application.platforms
    use_platform_suffix = use_platform_suffix or platforms != frozenset([current_platform])
    if use_jump and use_platform_suffix:
        logger.warning(f"Cannot use a custom scie jump build with a multi-platform configuration.")
        logger.warning(
            "Restricting requested platforms of "
            f"{', '.join(platform.value for platform in platforms)} to "
            f"{current_platform.value}",
        )
        platforms = frozenset([current_platform])

    scie_jump_version = application.scie_jump.version if application.scie_jump else None
    if scie_jump_version and scie_jump_version < version.parse("0.9.0"):
        # N.B.: The scie-jump 0.9.0 or later is needed to support cross-building against foreign
        # platform scie-jumps with "-sj".
        sys.exit(
            f"A scie-jump version of {scie_jump_version} was requested but {sys.argv[0]} "
            f"requires at least 0.9.0."
        )

    native_jump_path = (
        a_scie.custom_jump(repo_path=use_jump)
        if use_jump
        else a_scie.jump(platform=current_platform)
    )
    with _temporary_directory(cleanup=not preserve_sandbox) as td:
        for platform, lift_manifest in _export(
            application,
            file_mappings,
            invert_lazy_ids=frozenset(invert_lazy_ids),
            dest_dir=td,
            platforms=platforms,
            include_provenance=include_provenance,
            app_info=AppInfo.assemble(app_info),
        ):
            jump_path = (
                a_scie.custom_jump(repo_path=use_jump)
                if use_jump
                else a_scie.jump(specification=application.scie_jump, platform=platform)
            )
            platform_export_dir = lift_manifest.parent
            subprocess.run(
                args=[str(native_jump_path), "-sj", str(jump_path), lift_manifest],
                cwd=platform_export_dir,
                stdout=subprocess.DEVNULL,
                check=True,
            )
            src_binary_name = current_platform.binary_name(application.name)
            dst_binary_name = (
                platform.qualified_binary_name(application.name)
                if use_platform_suffix
                else platform.binary_name(application.name)
            )
            dest_dir.mkdir(parents=True, exist_ok=True)
            dst_binary = dest_dir / dst_binary_name
            shutil.move(src=platform_export_dir / src_binary_name, dst=dst_binary)
            if hash_functions:
                digests = tuple(hashlib.new(hash_function) for hash_function in hash_functions)
                with dst_binary.open(mode="rb") as fp:
                    for chunk in iter(lambda: fp.read(io.DEFAULT_BUFFER_SIZE), b""):
                        for digest in digests:
                            digest.update(chunk)
                for digest in digests:
                    dst_binary.with_name(f"{dst_binary.name}.{digest.name}").write_text(
                        f"{digest.hexdigest()} *{dst_binary_name}{os.linesep}"
                    )
            click.echo(dst_binary)


def main():
    # By default, click help messages expose the fact the app is written in Python. The resulting
    # program name (`python -m module` or `__main__.py`) is both confusing and unusable for the end
    # user since both the Python distribution and the code are hidden away in the nce cache. Since
    # we know we run as a scie in normal circumstances, use the SCIE_ARGV0 exported by the
    # scie-jump when present.
    _main(prog_name=os.environ.get("SCIE_ARGV0"))

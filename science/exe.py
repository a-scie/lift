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
from textwrap import dedent
from types import TracebackType
from typing import Any, BinaryIO, Iterable, Iterator, Mapping

import click
import click_log
from click_didyoumean import DYMGroup
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
    cls=DYMGroup,
    context_settings=dict(auto_envvar_prefix="SCIENCE", help_option_names=["-h", "--help"]),
)
@click.version_option(__version__, "-V", "--version", message="%(version)s")
@click.option(
    "-v",
    "--verbose",
    count=True,
    help=dedent(
        """\
        Increase output verbosity.

        Can be specified multiple times to further increase verbosity.
        """
    ),
)
@click.option(
    "-q",
    "--quiet",
    count=True,
    help=dedent(
        """\
        Decrease output verbosity.

        Can be specified multiple times to further decrease verbosity.
        """
    ),
)
def _main(verbose: int, quiet: int) -> None:
    """Science helps you prepare scies for your application.

    Science provides a high-level TOML manifest format for a scie application and can build scies
    and export scie lift JSON manifests from these configuration files.

    For more information on the TOML manifest format, see:
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

        bindings: list[Command] = []
        distributions: list[Distribution] = []

        requested_files: list[File] = []
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

        build_info = application.build_info if lift_config.include_provenance else None

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


@dataclass(frozen=True)
class LiftConfig:
    file_mappings: tuple[FileMapping, ...] = ()
    invert_lazy_ids: frozenset[str] = frozenset()
    include_provenance: bool = False
    app_info: tuple[AppInfo, ...] = ()
    app_name: str | None = None


pass_lift = click.make_pass_decorator(LiftConfig)


@_main.group(cls=DYMGroup, name="lift")
@click.option(
    "--file",
    "file_mappings",
    metavar="NAME=LOCATION",
    type=FileMapping.parse,
    multiple=True,
    default=[],
    envvar="SCIENCE_EXPORT_FILE",
    help=dedent(
        """\
        Map paths to files defined in your manifest.

        Science looks fore each non-lazy file you define at the path denoted by its name relative
        to the CWD you invoke science from. If any file is not at that path, you can tell science
        to look elsewhere with: `--file <name>=<location>`.

        For example, for this manifest snippet:

        \b
        [[lift.files]]
        name = "example.txt"

        If the file is located at `src/examples/example.txt` relative to the CWD you would specify
        `--file example.txt=src/examples/example.txt`.
        """
    ),
)
@click.option(
    "--invert-lazy",
    "invert_lazy_ids",
    metavar="FILE_ID",
    multiple=True,
    default=[],
    envvar="SCIENCE_EXPORT_INVERT_LAZY",
    help=dedent(
        """\
        Toggle the laziness of a file declared in the application lift manifest.

        For example, for this manifest snippet:

        \b
        [lift]
        name = "example"

        [[lift.interpreters]]
        id = "cpython"
        provider = "PythonBuildStandalone"
        version = "3.11"

        \b
        [[lift.files]]
        name = "example.txt"
        digest = { size = 137, fingerprint = "abcd1234" }}
        source = { url = "https://example.com", lazy = false }

        The default scie built will be "fat". Both the Python Build Standalone CPython 3.11
        interpreter distribution and the example.txt file will be downloaded by `science` and
        packed into the `example` (or `example.exe` on Windows) scie.

        To create a "skinny" scie in addition using this same application lift manifest you can
        specify:

        \b
        science lift --invert-lazy cpython --invert-lazy example.txt --name example-thin

        The resulting `example-thin` (or `example-thin.exe` on Windows) scie will include the
        `ptex` binary which will be used to fetch both the Python Build Standalone CPython 3.11
        interpreter distribution and the example.txt file upon first execution.

        Note: only interpreter distributions and files with url sources can be toggled. Trying to
        toggle the laziness for other file types, like those with either no source or a binding
        command source, will produce an informative error.
        """
    ),
)
@click.option(
    "--include-provenance",
    is_flag=True,
    help=dedent(
        """\
        Include provenance information for the build in the resulting scie lift JSON manifest.

        Provenance information for the `science` binary used to build the scie as well as
        provenance information for the lift manifest TOML used to create the scie will be included.

        If run in a git repository, the git state will be included in
        `git describe --always --dirty --long` format.

        If the application lift manifest has a `[lift.app_info]` table, all data in that table will
        be included. If any `--app-info` are specified, these top-level keys will also be included
        and over-ride any top level keys of the same name present in `[lift.app_info]`.

        For example, given the following application lift manifest snippet:

        \b
        [lift.app_info]
        provided_by = { sponsor = "example.org", licenses = ["Apache-2.0", "MIT"] }
        edition = "free"

        Running the following:

        \b
        science lift \\
            --include-provenance \\
            --app-info edition=paid \\
            --app-info releaser=$(id -un) \\
            export

        Would result in a scie lift JSON manifest with extra content like:

        \b
        {
          "scie": {
            ...
          },
          "science": {
            "app_info": {
              "edition" = "paid"
              "provided_by": {
                "licenses": [
                  "Apache-2.0",
                  "MIT"
                ],
                "releaser": "jsirois",
                "sponsor": "example.org"
              }
            },
            "binary": {
              "url": "https://github.com/a-scie/lift/releases/tag/v0.1.0/science-linux-x86_64",
              "version": "0.1.0"
            },
            "git_state": "v0.1.0-0-gc423e47",
            "manifest": {
              "hash": "49dc36a6db71bccf1bff35363454f7567fd124ba80d1e488bd320668a11c70bc",
              "size": 432,
              "source": "lift.toml"
            },
            "notes": [
              "This scie lift JSON manifest was generated from a source lift toml manifest using the science binary.",
              "Find out more here: https://github.com/a-scie/lift/blob/v0.1.0/README.md"
            ]
          }
        }
        """
    ),
)
@click.option(
    "--name",
    "app_name",
    help=dedent(
        """\
        Override the name of the application declared in the lift manifest.

        This is particularly useful in combination with `--invert-lazy` to produce both "skinny"
        and "fat" scies from the same lift manifest. See the `--invert-lazy` help for an example.
        """
    ),
)
@click.option(
    "--app-info",
    metavar="KEY=VALUE",
    type=AppInfo.parse,
    multiple=True,
    default=[],
    envvar="SCIENCE_EXPORT_APP_INFO",
    help=dedent(
        """\
        Override top-level `[lift.app_info]` keys or define new ones.

        Implies `--include-provenance` whose help provides an example.
        """
    ),
)
@click.pass_context
def _lift(
    ctx: click.Context,
    file_mappings: list[FileMapping],
    invert_lazy_ids: list[str],
    include_provenance: bool,
    app_name: str | None,
    app_info: list[AppInfo],
) -> None:
    """Perform operations against your application lift TOML manifest.

    For more information on the TOML manifest format, see:
    https://github.com/a-scie/lift/blob/main/docs/manifest.md
    """
    ctx.obj = LiftConfig(
        file_mappings=tuple(file_mappings),
        invert_lazy_ids=frozenset(invert_lazy_ids),
        include_provenance=include_provenance or bool(app_info),
        app_info=tuple(app_info),
        app_name=app_name,
    )


def config_arg():
    return click.argument(
        "config", metavar="LIFT_TOML_PATH", type=click.File("rb"), default="lift.toml"
    )


def dest_dir_option():
    return click.option(
        "--dest-dir",
        type=Path,
        default=Path.cwd(),
        help=dedent("The destination directory to output files to."),
    )


def use_platform_suffix_option():
    return click.option(
        "--use-platform-suffix",
        is_flag=True,
        help=dedent(
            """\
            Force science to use a platform suffix.

            Science will automatically use a platform suffix for disambiguation. When there is no
            ambiguity, you can force a suffix anyway by using this flag.

            The current platform suffixes are:

            \b
            {suffixes}

            * Indicates the current platform.
            """
        ).format(
            suffixes="\n".join(
                f"{'*' if platform == Platform.current() else ' '} {platform.value}"
                for platform in Platform
            )
        ),
    )


def parse_application(lift_config: LiftConfig, config: BinaryIO) -> Application:
    application = parse_config(config, source=config.name)
    if lift_config.app_name:
        application = dataclasses.replace(application, name=lift_config.app_name)
    return application


@dataclass(frozen=True)
class PlatformInfo:
    @classmethod
    def create(cls, application: Application, use_suffix: bool = False) -> PlatformInfo:
        current = Platform.current()
        use_suffix = use_suffix or application.platforms != frozenset([current])
        return cls(current=current, use_suffix=use_suffix)

    current: Platform
    use_suffix: bool


@_lift.command()
@config_arg()
@dest_dir_option()
@use_platform_suffix_option()
@pass_lift
def export(
    lift_config: LiftConfig,
    config: BinaryIO,
    dest_dir: Path,
    use_platform_suffix: bool,
) -> None:
    """Export the lift TOML manifest as one or more scie lift JSON manifests."""

    application = parse_application(lift_config, config)
    platform_info = PlatformInfo.create(application, use_suffix=use_platform_suffix)
    with _temporary_directory(cleanup=True) as td:
        for _, manifest_path in _export(lift_config, application, dest_dir=td):
            lift_manifest = dest_dir / (
                manifest_path.relative_to(td) if platform_info.use_suffix else manifest_path.name
            )
            lift_manifest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(
                manifest_path,
                lift_manifest,
            )
            click.echo(lift_manifest)


@_lift.command()
@config_arg()
@dest_dir_option()
@use_platform_suffix_option()
@click.option(
    "--preserve-sandbox",
    is_flag=True,
    help=dedent(
        """\
        Preserve the scie assembly sandbox and print its path to stderr.

        When `science` builds a scie it creates a temporary sandbox to house the exported JSON lift
        manifest and any application files that will be included in the scie. If you preserve the
        sandbox, the native `scie-jump` binary is also included such that you can change directory
        to the sandbox and run `scie-jump` (or `scie-jump.exe` on Windows) to test assembling the
        scie "by hand".
        """
    ),
)
@click.option(
    "--use-jump",
    metavar="REPO_PATH",
    type=Path,
    help=dedent(
        """\
        The path to a clone of the scie-jump repo.

        Mainly useful for testing new `scie-jump` fixes or integrating new `scie-jump` features
        into science. The canonical repo to clone is at https://github.com/a-scie/jump.
        """
    ),
)
@click.option(
    "--hash",
    "hash_functions",
    type=click.Choice(sorted(hashlib.algorithms_guaranteed)),
    multiple=True,
    default=[],
    envvar="SCIENCE_BUILD_HASH",
)
@pass_lift
def build(
    lift_config: LiftConfig,
    config: BinaryIO,
    dest_dir: Path,
    use_platform_suffix: bool,
    preserve_sandbox: bool,
    use_jump: Path | None,
    hash_functions: list[str],
) -> None:
    """Build scie executables from the lift TOML manifest."""

    application = parse_application(lift_config, config)
    platform_info = PlatformInfo.create(application, use_suffix=use_platform_suffix)

    platforms = application.platforms
    if use_jump and use_platform_suffix:
        logger.warning(f"Cannot use a custom scie jump build with a multi-platform configuration.")
        logger.warning(
            "Restricting requested platforms of "
            f"{', '.join(sorted(platform.value for platform in platforms))} to "
            f"{platform_info.current.value}",
        )
        platforms = frozenset([platform_info.current])

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
        else a_scie.jump(platform=platform_info.current)
    )
    with _temporary_directory(cleanup=not preserve_sandbox) as td:
        for platform, lift_manifest in _export(
            lift_config, application, dest_dir=td, platforms=platforms
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
            src_binary_name = platform_info.current.binary_name(application.name)
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
            if preserve_sandbox:
                (lift_manifest.parent / platform_info.current.binary_name("scie-jump")).symlink_to(
                    native_jump_path
                )
                click.secho(f"Sandbox preserved at {lift_manifest.parent}", fg="yellow")


def main():
    # By default, click help messages expose the fact the app is written in Python. The resulting
    # program name (`python -m module` or `__main__.py`) is both confusing and unusable for the end
    # user since both the Python distribution and the code are hidden away in the nce cache. Since
    # we know we run as a scie in normal circumstances, use the SCIE_ARGV0 exported by the
    # scie-jump when present.
    _main(prog_name=os.environ.get("SCIE_ARGV0"))

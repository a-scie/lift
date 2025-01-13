# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import textwrap
import traceback
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePath
from textwrap import dedent
from types import TracebackType
from typing import Any, BinaryIO, Callable
from urllib.parse import urlparse, urlunparse

import click
import click_log
from click_didyoumean import DYMGroup
from packaging import version
from packaging.version import Version

from science import __version__, providers
from science.commands import build, lift
from science.commands.complete import Shell
from science.commands.doc import SERVER_NAME, LaunchError
from science.commands.doc import launch as launch_doc_server
from science.commands.doc import shutdown as shutdown_doc_server
from science.commands.download import download_a_scie_executables, download_provider_distribution
from science.commands.lift import AppInfo, FileMapping, LiftConfig, PlatformInfo
from science.config import parse_config
from science.context import DocConfig, ScienceConfig
from science.doc import DOC_SITE_URL
from science.errors import InputError
from science.fs import temporary_directory
from science.model import Application
from science.options import OptionDescriptor, mutually_exclusive, to_option_string
from science.os import EXE_EXT
from science.platform import CURRENT_PLATFORM, Platform
from science.providers import ALL_PROVIDERS, ProviderInfo

logger = logging.getLogger(__name__)

SCIE_ARGV0 = os.environ.get("SCIE_ARGV0")


def _log_fatal(
    type_: type[BaseException],
    value: BaseException,
    tb: TracebackType,
    *,
    always_include_backtrace: bool,
) -> None:
    if always_include_backtrace or not isinstance(value, InputError):
        click.secho("".join(traceback.format_tb(tb)), fg="yellow", err=True, nl=False)
        click.secho(f"{type_.__module__}.{type_.__qualname__}: ", fg="yellow", err=True, nl=False)
    click.secho(value, fg="red", err=True)


SEE_MANIFEST_HELP = (
    f"For more information on the TOML manifest format, see: {DOC_SITE_URL}/manifest.html"
)


@click.group(
    cls=DYMGroup,
    context_settings=dict(auto_envvar_prefix="SCIENCE", help_option_names=["-h", "--help"]),
    help=dedent(
        f"""\
        Science helps you prepare scies for your application.

        Science provides a high-level TOML manifest format for a scie application and can build scies
        and export scie lift JSON manifests from these configuration files.

        {SEE_MANIFEST_HELP}
        """
    ),
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
@click.option(
    "--cache-dir",
    type=Path,
    default=ScienceConfig.DEFAULT_CACHE_DIR,
    show_default=True,
    help="Specify an alternate location for the science cache.",
)
@click.pass_context
def _main(ctx: click.Context, verbose: int, quiet: int, cache_dir: Path) -> None:
    # N.B.: Help is defined above in the _main group decorator since it's a dynamic string.
    science_config = ScienceConfig(verbosity=verbose - quiet, cache_dir=cache_dir)
    science_config.configure_logging(root_logger=click_log.basic_config())
    sys.excepthook = functools.partial(_log_fatal, always_include_backtrace=science_config.verbose)
    ctx.obj = science_config


@_main.command(name="complete")
@click.option(
    "--shell",
    default=shell.value if (shell := Shell.current()) else None,
    type=click.Choice([shell.value for shell in Shell]),
    show_default=Shell.current() is not None,
    callback=lambda _ctx, _param, value: Shell(value),
    required=Shell.current() is None,
    help="Specify the shell to generate a completion script for.",
)
@click.option(
    "--output", type=click.File("wb"), help="The file to output the shell completion script to."
)
def _complete(shell: Shell, output: BytesIO | None) -> None:
    """Generate shell completion scripts.

    By default, the appropriate shell completion script for the current shell is output to stdout,
    but both the shell and output destination can be altered.

    The use of the script depends on your shell type and preferences. To test things out you can
    use:

    * `bash` or `zsh`::

        \b
        eval "$(science complete)"

    * `fish`::

        \b
        eval (science complete)

    To trigger option completion you must type `-` before tabbing.

    .. note::
     If science cannot detect your shell, or it can but is not one of the supported shells for
     completion, you must specify `--shell`.
    """
    if not SCIE_ARGV0:
        raise InputError("Can only generate completion scripts when run from a scie.")

    env_var_bin_name = SCIE_ARGV0.rstrip(EXE_EXT).replace("-", "_").upper()
    sys.exit(
        subprocess.run(
            [SCIE_ARGV0],
            env={**os.environ, f"_{env_var_bin_name}_COMPLETE": f"{shell.value}_source"},
            stdout=output.fileno() if output else None,
        ).returncode
    )


pass_doc = click.make_pass_decorator(DocConfig)


@_main.group(cls=DYMGroup, name="doc")
@click.option(
    "--site",
    default=DOC_SITE_URL,
    show_default=True,
    help="Specify an alternate URL of the doc site.",
)
@click.option("--local", type=Path, hidden=True)  # N.B.: Set via env var by the lift manifest.
@click.pass_context
def _doc(ctx: click.Context, site: str, local: Path | None) -> None:
    """Interact with science docs."""
    ctx.obj = DocConfig(site=site, local=local)


@_doc.command(name="open")
@click.option(
    "--remote",
    is_flag=True,
    help=dedent(
        f"""\
        Open the official remote doc site instead.

        N.B.: The official docs track the latest release of science. You're using {__version__},
        which may not match.
        """
    ),
)
@click.argument("page", default=None, required=False)
@pass_doc
@click.pass_context
def _open_doc(ctx: click.Context, doc: DocConfig, remote: bool, page: str | None = None) -> None:
    """Opens the local documentation in a browser.

    If an optional page argument is supplied, that page will be opened instead of the default doc
    site page.

    Documentation is served by a local HTTP server which you can shut down with `science doc close`.
    """
    if remote or not doc.local:
        url = doc.site
    else:
        try:
            launch_result = launch_doc_server(document_root=doc.local)
        except LaunchError:
            try:
                launch_result = launch_doc_server(document_root=doc.local, port=0)
            except LaunchError as e:
                with open(e.log) as fp:
                    for line in fp:
                        logger.error(line.rstrip())
                logger.fatal(f"Failed to launch {SERVER_NAME}.")
                ctx.exit(1)
                return

        url = launch_result.server_info.url
        if launch_result.already_running:
            click.secho(
                f"Using {SERVER_NAME} already running at {launch_result.server_info}.",
                fg="cyan",
                err=True,
            )
        else:
            click.secho(
                f"Launched {SERVER_NAME} at {launch_result.server_info}", fg="green", err=True
            )

    if not page:
        if not remote:
            url = f"{url}/index.html"
    else:
        url_info = urlparse(url)
        page = f"{page}.html" if not PurePath(page).suffix else page
        url = urlunparse(url_info._replace(path=f"{url_info.path}/{page}"))

    click.launch(url)


@_doc.command(name="close")
def _close_doc() -> None:
    """Shuts down the local documentation server."""
    server_info = shutdown_doc_server()
    if server_info:
        click.secho(f"Shut down the {SERVER_NAME} at {server_info}.", fg="green", err=True)
    else:
        click.secho("No documentation server was running.", fg="cyan", err=True)


@dataclass(frozen=True)
class DownloadConfig:
    platforms: tuple[Platform, ...]
    explicit_set: bool


pass_download = click.make_pass_decorator(DownloadConfig)

platform_mutex_check = mutually_exclusive(
    OptionDescriptor("platforms", flag="--platform"), "all_platforms"
)


@_main.group(cls=DYMGroup, name="download")
@click.option(
    "--platform",
    "platforms",
    type=Platform.parse,
    multiple=True,
    default=[],
    callback=platform_mutex_check,
    help=(
        "Download binaries for the specified platform(s). Mutually exclusive with "
        "`--all-platforms`. By default, only binaries for the current platform are downloaded."
    ),
)
@click.option(
    "--all-platforms",
    is_flag=True,
    default=False,
    callback=platform_mutex_check,
    help=(
        "Download binaries for all platforms science supports. Mutually exclusive with "
        "`--platform`. By default, only binaries for the current platform are downloaded."
    ),
)
@click.pass_context
def _download(ctx: click.Context, platforms: list[Platform], all_platforms: bool) -> None:
    """Download binaries for offline use."""

    if platforms:
        platforms = list(dict.fromkeys(platforms))
        explicit_set = True
    elif all_platforms:
        platforms = list(Platform)
        explicit_set = False
    else:
        platforms = [CURRENT_PLATFORM]
        explicit_set = True

    ctx.obj = DownloadConfig(platforms=tuple(platforms), explicit_set=explicit_set)


download_dest_dir = click.argument("dest_dir", metavar="DEST_DIR", type=Path)


@_download.group(cls=DYMGroup, name="provider")
def _download_provider() -> None:
    """Download distributions from providers for offline use."""


def _create_provider_download_func(
    provider_info: ProviderInfo,
) -> Callable[[DownloadConfig, Path], None]:
    @_download_provider.command(name=provider_info.short_name)
    @download_dest_dir
    @pass_download
    def func(download_config: DownloadConfig, dest_dir: Path, **kwargs: Any) -> None:
        download_provider_distribution(
            provider_info=provider_info,
            platforms=download_config.platforms,
            explicit_platforms=download_config.explicit_set,
            dest_dir=dest_dir,
            **kwargs,
        )

    setattr(func, "__name__", provider_info.name.replace(".", "_"))
    func.__doc__ = f"Download {provider_info.name} distributions for offline use."

    for field in provider_info.config_fields():
        assert field.type.has_origin_type or callable(getattr(field.type, "parse", None)), (
            f"Expected {provider_info.name} config fields to be simple scalar types or else have a "
            f"`parse(str)` factory function. Field {field.name} has type {field.type} which is "
            f"neither."
        )
        func = click.option(
            to_option_string(field.name),
            type=field.type.origin_type,
            required=field.default is dataclasses.MISSING,
            multiple=True,
            default=[],
            help=(
                f"{field.doc} [default: {field.default}]"
                if (field.default and field.default is not dataclasses.MISSING)
                else field.doc
            ),
        )(func)

    return func


for _provider_info in ALL_PROVIDERS:
    _create_provider_download_func(_provider_info)

download_a_scie_versions = click.option(
    "--version",
    "versions",
    type=Version,
    multiple=True,
    default=[],
    help="One or more versions to download. By default, the latest version is downloaded.",
)


@_download.command(name="ptex")
@download_dest_dir
@download_a_scie_versions
@pass_download
def _download_ptex(
    download_config: DownloadConfig, dest_dir: Path, versions: list[Version]
) -> None:
    """Download ptex binaries for offline use."""
    download_a_scie_executables(
        project_name="ptex",
        binary_name="ptex",
        versions=versions,
        platforms=download_config.platforms,
        dest_dir=dest_dir,
    )


@_download.command(name="scie-jump")
@download_dest_dir
@download_a_scie_versions
@pass_download
def _download_scie_jump(
    download_config: DownloadConfig, dest_dir: Path, versions: list[Version]
) -> None:
    """Download scie-jump binaries for offline use."""
    download_a_scie_executables(
        project_name="jump",
        binary_name="scie-jump",
        versions=versions,
        platforms=download_config.platforms,
        dest_dir=dest_dir,
    )


@_main.group(cls=DYMGroup, name="provider")
def _provider() -> None:
    """Perform operations against provider plugins."""


@_provider.command(name="list")
@click.option(
    "--json",
    "emit_json",
    is_flag=True,
    help="Output the list of providers as a JSON list of objects",
)
def _list(emit_json: bool) -> None:
    """List the installed provider plugins."""
    if emit_json:
        click.echo(
            json.dumps(
                [
                    {
                        "type": provider_info.fully_qualified_name,
                        "source": provider_info.source,
                        "short_name": provider_info.short_name,
                        "summary": provider_info.summary,
                        "description": provider_info.description,
                    }
                    for provider_info in providers.ALL_PROVIDERS
                ],
                sort_keys=True,
            )
        )
        return

    indent_width = len(f"{len(providers.ALL_PROVIDERS)}. ")
    indent = " " * indent_width
    for index, provider_info in enumerate(providers.ALL_PROVIDERS, start=1):
        if index > 1:
            click.echo()
        index_prefix = f"{index}.".ljust(indent_width)
        click.echo(f"{index_prefix}{provider_info.fully_qualified_name}")
        click.echo(f"{indent}source: {provider_info.source}")
        if provider_info.short_name:
            click.echo(f"{indent}short name: {provider_info.short_name}")
        if provider_info.summary:
            click.echo()
            click.echo(f"{indent}{provider_info.summary}")
        if provider_info.description:
            click.echo()
            click.echo(textwrap.indent(provider_info.description, prefix=indent))


pass_lift = click.make_pass_decorator(LiftConfig)


@_main.group(
    cls=DYMGroup,
    name="lift",
    help=dedent(
        f"""\
        Perform operations against your application lift TOML manifest.

        {SEE_MANIFEST_HELP}
        """
    ),
)
@click.option(
    "--file",
    "file_mappings",
    metavar="NAME=LOCATION",
    type=FileMapping.parse,
    multiple=True,
    default=[],
    help=dedent(
        """\
        Map paths to files defined in your manifest.

        Science looks fore each non-lazy file you define at the path denoted by its name relative
        to the CWD you invoke science from. If any file is not at that path, you can tell science
        to look elsewhere with: `--file <name>=<location>`.

        For example, for this manifest snippet::

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
    help=dedent(
        """\
        Toggle the laziness of a file declared in the application lift manifest.

        For example, for this manifest snippet::

         \b
         [lift]
         name = "example"
         \b
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
        specify::

         \b
         science lift --invert-lazy cpython --invert-lazy example.txt --app-name example-thin

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

        For example, given the following application lift manifest snippet::

         \b
         [lift.app_info]
         provided_by = { sponsor = "example.org", licenses = ["Apache-2.0", "MIT"] }
         edition = "free"

        Running the following::

         \b
         science lift \\
             --include-provenance \\
             --app-info edition=paid \\
             --app-info releaser=$(id -un) \\
             export

        Would result in a scie lift JSON manifest with extra content like::

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
               "This scie lift JSON manifest was generated from lift.toml using the science binary.",
               "Find out more here: $DOC_SITE_URL$"
             ]
           }
         }
        """.replace("$DOC_SITE_URL$", DOC_SITE_URL)  # A few too many {} to escape them all.
    ),
)
@click.option(
    "--app-name",
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
    help=dedent(
        """\
        Override top-level `[lift.app_info]` keys or define new ones.

        Implies `--include-provenance` whose help provides an example.
        """
    ),
)
@click.option(
    "--platform",
    "platforms",
    type=Platform.parse,
    multiple=True,
    default=[],
    help="Override any configured platforms and target these platforms instead.",
)
@click.pass_context
def _lift(
    ctx: click.Context,
    file_mappings: list[FileMapping],
    invert_lazy_ids: list[str],
    include_provenance: bool,
    app_name: str | None,
    app_info: list[AppInfo],
    platforms: list[Platform],
) -> None:
    # N.B.: Help is defined above in the _lift group decorator since it's a dynamic string.
    ctx.obj = LiftConfig(
        file_mappings=tuple(file_mappings),
        invert_lazy_ids=frozenset(invert_lazy_ids),
        include_provenance=include_provenance or bool(app_info),
        app_info=tuple(app_info),
        app_name=app_name,
        platforms=tuple(platforms),
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
        show_default=True,
        help=dedent("The destination directory to output files to."),
    )


def use_platform_suffix_option():
    return click.option(
        "--use-platform-suffix/--no-use-platform-suffix",
        default=None,
        help=dedent(
            """\
            Force science to use a platform suffix or omit one.

            Science will automatically use a platform suffix for disambiguation. When there is no
            ambiguity, you can force a suffix anyway with `--use-platform-suffix`. Likewise, you
            can suppress inclusion of a platform suffix with `--no-use-platform-suffix`.

            The current platform suffixes are::

             \b
             {suffixes}

            * Indicates the current platform.
            """
        ).format(
            suffixes="\n ".join(
                f"{"*" if platform == CURRENT_PLATFORM else " "} {platform.value}"
                for platform in Platform
            )
        ),
    )


def parse_application(lift_config: LiftConfig, config: BinaryIO) -> Application:
    application = parse_config(config, source=config.name)
    if lift_config.app_name:
        # MyPy does not handle dataclass_transform yet: https://github.com/python/mypy/issues/14293
        application = dataclasses.replace(application, name=lift_config.app_name)  # type: ignore[misc]
    return application


@_lift.command()
@config_arg()
@dest_dir_option()
@use_platform_suffix_option()
@pass_lift
def export(
    lift_config: LiftConfig,
    config: BinaryIO,
    dest_dir: Path,
    use_platform_suffix: bool | None,
) -> None:
    """Export the lift TOML manifest as one or more scie lift JSON manifests."""

    application = parse_application(lift_config, config)
    platform_info = PlatformInfo.create(application, use_suffix=use_platform_suffix)
    with temporary_directory(cleanup=True) as td:
        for _, manifest_path in lift.export_manifest(
            lift_config, application, dest_dir=td, platforms=lift_config.platforms
        ):
            lift_manifest = dest_dir / (
                manifest_path.relative_to(td) if platform_info.use_suffix else manifest_path.name
            )
            lift_manifest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(
                manifest_path,
                lift_manifest,
            )
            click.echo(lift_manifest)


@_lift.command(name="build")
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
    help=dedent(
        """\
        Output a checksum file compatible with the shasum family of tools.

        For each unique `--hash` specified, a sibling file to the scie executable will be generated
        with the same name and hash algorithm name suffix. The file will contain the hex fingerprint
        of the scie executable using that algorithm to hash it.

        For example, for `--hash sha256` against a scie named example on Windows you might get::

         \b
         dist/example.exe
         dist/example.exe.sha256

        The contents of `dist/example.exe.sha256` would look like (`*` means executable)::

         \b
         33fd890f056b0434241a357b616b4a651c82acc1ee4ce42e0b95c059d4a76f04 *example.exe

        And the fingerprint of `example.exe` could be checked by running the following in the
        `dist` dir::

         \b
         sha256sum -c example.exe.sha256
         example.exe: OK
        """
    ),
)
@pass_lift
def _build(
    lift_config: LiftConfig,
    config: BinaryIO,
    dest_dir: Path,
    use_platform_suffix: bool | None,
    preserve_sandbox: bool,
    use_jump: Path | None,
    hash_functions: list[str],
) -> None:
    """Build scie executables from the lift TOML manifest.

    If the LIFT_TOML_PATH is left unspecified, `lift.toml` is assumed.
    """

    application = parse_application(lift_config, config)
    platform_info = PlatformInfo.create(application, use_suffix=use_platform_suffix)

    platforms = lift_config.platforms or application.platforms
    if use_jump and use_platform_suffix:
        logger.warning("Cannot use a custom scie jump build with a multi-platform configuration.")
        logger.warning(
            "Restricting requested platforms of "
            f"{", ".join(sorted(platform.value for platform in platforms))} to {CURRENT_PLATFORM}",
        )
        platforms = frozenset([CURRENT_PLATFORM])

    scie_jump_version = application.scie_jump.version if application.scie_jump else None
    if scie_jump_version and scie_jump_version < version.parse("0.9.0"):
        # N.B.: The scie-jump 0.9.0 or later is needed to support cross-building against foreign
        # platform scie-jumps with "-sj".
        sys.exit(
            f"A scie-jump version of {scie_jump_version} was requested but {sys.argv[0]} "
            f"requires at least 0.9.0."
        )

    with temporary_directory(cleanup=not preserve_sandbox) as td:
        assembly_info = build.assemble_scies(
            lift_config=lift_config,
            application=application,
            dest_dir=td,
            platforms=platforms,
            platform_info=platform_info,
            use_jump=use_jump,
            hash_functions=hash_functions,
        )
        dest_dir.mkdir(parents=True, exist_ok=True)

        def move(path: Path) -> None:
            dst = dest_dir / path.name
            shutil.move(src=path, dst=dst)
            click.echo(dst)

        for scie_assembly in assembly_info.scies:
            move(scie_assembly.scie)
            for checksum_file in scie_assembly.hashes:
                move(checksum_file)

            if preserve_sandbox:
                (scie_assembly.lift_manifest.parent / assembly_info.native_jump.name).symlink_to(
                    assembly_info.native_jump
                )
                click.secho(
                    f"Sandbox preserved at {scie_assembly.lift_manifest.parent}", fg="yellow"
                )


def main():
    # By default, click help messages expose the fact the app is written in Python. The resulting
    # program name (`python -m module` or `__main__.py`) is both confusing and unusable for the end
    # user since both the Python distribution and the code are hidden away in the nce cache. Since
    # we know we run as a scie in normal circumstances, use the SCIE_ARGV0 exported by the
    # scie-jump when present.
    _main(prog_name=SCIE_ARGV0)

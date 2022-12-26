# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import subprocess
import tempfile
from pathlib import Path

import click

from science import __version__, jump, lift, ptex
from science.config import parse_config_file
from science.model import Command, File
from science.platform import Platform


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(__version__, "-V", "--version", message="%(version)s")
def main() -> None:  # TODO(John Sirois): XXX:
    # Expose
    # // --platform ... selection
    #
    # --python ... selection (lazy)
    # --python PBS(release=X,version=Y,flavor=Z)
    # --java ... selection (lazy)
    # --js ... selection (lazy)
    #
    # Interpreter provider PBS, needs 3 parameters to select a release and 1 parameter to select
    # platform. It the provides {python} which is mapped to scie-jump placeholder per-platform.
    #
    # TODO(John Sirois): XXX: How to reference files from above
    #  Also, when the reference is platform specific, then this seems to fall apart.
    # --exe --args --env
    pass


@main.command()
@click.option(
    "-p",
    "--platform",
    "platforms",
    type=Platform.parse,
    multiple=True,
    default=[Platform.current()],
)
def init(platforms: tuple[Platform, ...]) -> None:
    click.echo(f"Science init!:")
    click.echo(f"{platforms=}")


@main.command()
@click.option("--config", type=Path)
@click.option("--file", "file_mappings", multiple=True, default=[])
@click.option("--dest-dir", type=Path, default=Path.cwd())
def build(config: Path, file_mappings: list[str], dest_dir: Path) -> None:
    application = parse_config_file(config)

    for platform in application.platforms:
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            jump_path = jump.load(temp_dir, platform)

            files: list[File] = []
            fetch = any("fetch" == file.source for file in application.files)
            fetch |= any(interpreter.lazy for interpreter in application.interpreters)
            if fetch:
                files.append(ptex.load(temp_dir, platform))
            for interpreter in application.interpreters:
                distribution = interpreter.provider.distribution(platform)
                if distribution:
                    files.append(distribution.file)
            files.extend(application.files)

            commands: list[Command] = []
            bindings: list[Command] = []
            lift_path = lift.emit_manifest(temp_dir, files, commands, bindings)
            subprocess.run(args=[str(jump_path), str(lift_path)], cwd=td, check=True)


if __name__ == "__main__":
    main()

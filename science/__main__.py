# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
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


@dataclass(frozen=True)
class FileMapping:
    @classmethod
    def parse(cls, value: str) -> FileMapping:
        components = value.split(" ", 1)
        if len(components) != 2:
            raise ValueError(
                "Invalid file mapping. A file mapping must be of the form "
                f"`(<name>|<key>)=<path>`: {value}"
            )
        return cls(id=components[0], path=Path(components[1]))

    id: str
    path: Path


@main.command()
@click.option("--config", type=Path)
@click.option("--file", "file_mappings", type=FileMapping, multiple=True, default=[])
@click.option("--dest-dir", type=Path, default=Path.cwd())
def build(config: Path, file_mappings: list[FileMapping], dest_dir: Path) -> None:
    application = parse_config_file(config)

    use_platform_suffix = application.platforms != frozenset([Platform.current()])
    for platform in application.platforms:
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            jump_path = jump.load(platform)

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

            file_paths_by_id = {
                file_mapping.id: file_mapping.path for file_mapping in file_mappings
            }
            for file in files:
                path = file_paths_by_id.get(file.id) or Path.cwd() / file.name
                if not path.exists():
                    raise ValueError(f"The file for {file.id} is not mapped or cannot be found.")
                path.symlink_to(temp_dir / file.name)

            lift_path = lift.emit_manifest(
                temp_dir, files, application.commands, application.bindings
            )
            subprocess.run(args=[str(jump_path), str(lift_path)], cwd=td, check=True)
            src_binary_name = platform.binary_name(application.name)
            dst_binary_name = (
                platform.qualified_binary_name(application.name)
                if use_platform_suffix
                else platform.binary_name(application.name)
            )
            shutil.move(src=temp_dir / src_binary_name, dst=dest_dir / dst_binary_name)


if __name__ == "__main__":
    main()

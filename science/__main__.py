# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import click

from science import __version__, a_scie, lift
from science.config import parse_config_file
from science.model import Command, Distribution, File, Url
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
        components = value.split("=", 1)
        if len(components) != 2:
            raise ValueError(
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


@main.command()
@click.option("--config", type=Path)
@click.option("--file", "file_mappings", type=FileMapping.parse, multiple=True, default=[])
@click.option("--dest-dir", type=Path, default=Path.cwd())
@click.option("--preserve-sandbox", is_flag=True)
def build(
    config: Path, file_mappings: list[FileMapping], dest_dir: Path, preserve_sandbox: bool
) -> None:
    application = parse_config_file(config)

    current_platform = Platform.current()
    use_platform_suffix = application.platforms != frozenset([current_platform])
    # N.B.: The scie-jump 0.9.0 or later is needed to support cross-building against foreign
    # platform scie-jumps with "-sj".
    native_jump_path = a_scie.jump(platform=current_platform)
    for platform in application.platforms:
        with _temporary_directory(cleanup=not preserve_sandbox) as td:
            temp_dir = Path(td)
            jump_path = a_scie.jump(platform=platform)

            bindings: list[Command] = []
            distributions: list[Distribution] = []
            files: list[File] = []
            file_paths_by_id = {
                file_mapping.id: file_mapping.path.resolve() for file_mapping in file_mappings
            }
            fetch_urls: dict[str, str] = {}
            fetch = any("fetch" == file.source for file in application.files)
            fetch |= any(interpreter.lazy for interpreter in application.interpreters)
            if fetch:
                ptex = a_scie.ptex(temp_dir, platform=platform)
                file_paths_by_id[ptex.id] = temp_dir / ptex.name
                files.append(ptex)
                bindings.append(
                    Command(name="fetch", exe=ptex.placeholder, args=tuple(["{scie.lift}"]))
                )
            bindings.extend(application.bindings)

            for interpreter in application.interpreters:
                distribution = interpreter.provider.distribution(platform)
                if distribution:
                    distributions.append(distribution)
                    files.append(distribution.file)
                    match distribution.source:
                        case Url(url):
                            fetch_urls[distribution.file.name] = url
                        case path:
                            file_paths_by_id[distribution.file.id] = path
            files.extend(application.files)

            for file in files:
                if file.source is None:
                    path = file_paths_by_id.get(file.id) or Path.cwd() / file.name
                    if not path.exists():
                        raise ValueError(
                            f"The file for {file.id} is not mapped or cannot be found."
                        )
                    target = temp_dir / file.name
                    if not target.exists():
                        target.symlink_to(path)

            lift_path = lift.emit_manifest(
                temp_dir,
                name=application.name,
                description=application.description,
                load_dotenv=application.load_dotenv,
                distributions=distributions,
                files=files,
                commands=application.commands,
                bindings=bindings,
                fetch_urls=fetch_urls,
            )
            subprocess.run(
                args=[str(native_jump_path), "-sj", str(jump_path), str(lift_path)],
                cwd=td,
                check=True,
            )
            src_binary_name = current_platform.binary_name(application.name)
            dst_binary_name = (
                platform.qualified_binary_name(application.name)
                if use_platform_suffix
                else platform.binary_name(application.name)
            )
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(src=temp_dir / src_binary_name, dst=dest_dir / dst_binary_name)


if __name__ == "__main__":
    main()

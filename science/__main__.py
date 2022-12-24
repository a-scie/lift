# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pathlib import Path, PurePath
from urllib.parse import urlparse

import click

from science import __version__
from science.fetcher import fetch_and_verify
from science.platform import Platform


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(__version__, "-V", "--version", message="%(version)s")
def main() -> None:  # TODO(John Sirois): XXX:
    # Expose
    # --platform ... selection
    # --python ... selection (lazy)
    # --java ... selection (lazy)
    # --js ... selection (lazy)
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
def build() -> None:
    click.echo("Science build!")


@main.command()
@click.option("-x", "--executable", is_flag=True, default=False)
@click.argument("url")
def download(url: str, executable: bool = False) -> None:
    fetch_and_verify(url, Path.cwd() / PurePath(urlparse(url).path).name, executable=executable)


if __name__ == "__main__":
    main()

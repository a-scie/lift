# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pathlib import Path

from science.fetcher import fetch_and_verify
from science.model import File
from science.platform import Platform


def load(
    dest_dir: Path, platform: Platform = Platform.current(), version: str | None = None
) -> File:
    binary_name = platform.qualified_binary_name("ptex")
    base_url = "https://github.com/a-scie/ptex/releases"
    version_path = f"download/v{version}" if version else "latest/download"
    fetch_and_verify(
        url=f"{base_url}/{version_path}/{binary_name}", dest=dest_dir / binary_name, executable=True
    )
    return File(name=binary_name, key="ptex", is_executable=True)

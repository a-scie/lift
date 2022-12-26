# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pathlib import Path

from science.fetcher import fetch_and_verify
from science.model import File
from science.platform import Platform


def load(temp_dir: Path, platform: Platform, version: str | None = None) -> File:
    extension = ".exe" if platform == Platform.Windows_x86_64 else ""
    binary_name = f"ptex-{platform}{extension}"
    base_url = "https://github.com/a-scie/ptex/releases"
    version_path = f"download/v{version}" if version else "latest/download"
    fetch_and_verify(
        url=f"{base_url}/{version_path}/{binary_name}", dest=temp_dir / binary_name, executable=True
    )
    return File(name=binary_name, key="ptex", is_executable=True)

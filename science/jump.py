# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pathlib import Path

from science.fetcher import fetch_and_verify
from science.platform import Platform


def load(platform: Platform = Platform.current(), version: str | None = None) -> Path:
    binary_name = platform.qualified_binary_name("scie-jump")
    base_url = "https://github.com/a-scie/jump/releases"
    version_path = f"download/v{version}" if version else "latest/download"
    return fetch_and_verify(url=f"{base_url}/{version_path}/{binary_name}", executable=True)

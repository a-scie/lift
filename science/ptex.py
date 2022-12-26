# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pathlib import Path

from science.model import File
from science.platform import Platform


def load(temp_dir: Path, platform: Platform) -> File:
    # TODO(John Sirois): XXX: Implement
    extension = ".exe" if platform == Platform.Windows_x86_64 else ""
    return File(name=f"ptex-{platform}{extension}", is_executable=True)

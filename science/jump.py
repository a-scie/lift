# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pathlib import Path

from science.platform import Platform


def load(temp_dir: Path, platform: Platform) -> Path:
    # TODO(John Sirois): XXX: Implement
    extension = ".exe" if platform == Platform.Windows_x86_64 else ""
    return temp_dir / f"scie-jump-{platform}{extension}"

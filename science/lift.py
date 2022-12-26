# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pathlib import Path
from typing import Iterable

from science.model import Command, File


def emit_manifest(
    temp_dir: Path, files: Iterable[File], commands: Iterable[Command], bindings: Iterable[Command]
) -> Path:
    # TODO(John Sirois): XXX: Implement
    return temp_dir / "lift.json"

# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import pprint
import sys
from pathlib import Path

from science.config import parse_config_file
from science.platform import Platform


def test_parse(build_root: Path) -> None:
    app = parse_config_file(build_root / "science.toml")
    pprint.pp(app, stream=sys.stderr, indent=2)
    for interpreter in app.interpreters:
        pprint.pp(
            interpreter.provider.distribution(Platform.current()), stream=sys.stderr, indent=2
        )

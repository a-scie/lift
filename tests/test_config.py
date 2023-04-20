# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os.path
import subprocess
import sys
from importlib import resources
from pathlib import Path

from science.config import parse_config_file
from science.model import Identifier
from science.platform import Platform


def test_parse(build_root: Path) -> None:
    app = parse_config_file(build_root / "science.toml")
    interpreters = list(app.interpreters)
    assert 1 == len(interpreters), "Expected science to ship on a single fixed interpreter."

    interpreter = interpreters[0]
    assert interpreter.lazy, "Expected science to ship as a gouged-out binary."

    distribution = interpreter.provider.distribution(Platform.current())
    assert (
        distribution is not None
    ), "Expected a Python interpreter distribution to be available for each platform tests run on."
    assert (
        Identifier.parse("python") in distribution.placeholders
    ), "Expected the Python interpreter to expose a 'python' placeholder for its `python` binary."


def test_interpreter_groups(tmpdir) -> None:
    with resources.path("data", "interpreter-groups.toml") as config:
        app = parse_config_file(config)
        assert app is not None, "TODO(John Sirois): XXX: Proper config test instead of IT below."

        subprocess.run(
            args=[sys.executable, "science.pex", "build", "--dest-dir", str(tmpdir), config],
            check=True,
        )

        exe_path = os.path.join(str(tmpdir), "igs")
        subprocess.run(args=[exe_path], env={**os.environ, "SCIE": "inspect"}, check=True)
        subprocess.run(
            args=[exe_path],
            env={**os.environ, "PYTHON": "cpython311", "RUST_LOG": "trace"},
            check=True,
        )

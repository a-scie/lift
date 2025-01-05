# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os
import sys
from pathlib import Path
from typing import Any

import colors
from packaging.version import InvalidVersion, Version

from science.config import parse_config_file
from science.errors import InputError
from science.providers import PyPy, PythonBuildStandalone


def main() -> Any:
    python_version_file = Path(".python-version")
    try:
        python_version = Version(python_version_file.read_text().strip())
    except OSError as e:
        return f"Couldn't read {python_version_file}: {e}"
    except InvalidVersion as e:
        return f"The python version in {python_version_file} could not be parsed: {e}"

    science_lift_manifest = Path("lift.toml")
    try:
        science_application = parse_config_file(science_lift_manifest)
    except InputError as e:
        return f"Failed to parse science lift manifest {science_lift_manifest}: {e}"

    python_interpreter_versions = tuple(
        py.provider.version
        for py in science_application.interpreters
        if isinstance(py.provider, (PyPy, PythonBuildStandalone))
    )
    error_message_lead_in = (
        f"Expected the science lift manifest at {science_lift_manifest} to have one or more "
        f"Python interpreters matching the {python_version_file} of {python_version}."
    )
    if not python_interpreter_versions:
        return os.linesep.join(
            (error_message_lead_in, "There were no python interpreters defined.")
        )
    if not all(version == python_version for version in python_interpreter_versions):
        versions = "versions" if len(python_interpreter_versions) > 1 else "version"
        version_list = ", ".join(map(str, python_interpreter_versions))
        return os.linesep.join((error_message_lead_in, f"Found {versions}: {version_list}"))

    prefix = f"Science lift manifest {science_lift_manifest} matches {python_version_file}"
    print(
        f"{colors.green(prefix)}: {colors.color(str(python_version), fg='green', style='bold')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

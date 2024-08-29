# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

# N.B.: This script is used by noxfile.py to check that its internal PBS_* constants match
# corresponding lift.toml values. It will be run by the PBS interpreter used to power the science
# binary and so it can safely use the syntax and stdlib of that interpreter, which is currently
# CPython 3.12.

import os
import sys
import tomllib
from argparse import ArgumentParser
from pathlib import Path
from textwrap import dedent
from typing import Any


def check_manifest(
    manifest_path: Path,
    *,
    expected_release: str,
    expected_version: str,
    expected_flavor: str
) -> str | None:
    with manifest_path.open("rb") as fp:
        manifest = tomllib.load(fp)

    interpreters = manifest["lift"]["interpreters"]
    if 1 != len(interpreters):
        return f"Expected lift.toml to define one interpreter but found {len(interpreters)}"
    interpreter = interpreters[0]

    errors = []
    if "PythonBuildStandalone" != (provider := interpreter.get("provider", "<missing>")):
        errors.append(f"Expected interpreter provider of PythonBuildStandalone but was {provider}.")
    if expected_release != (release := interpreter.get("release", "<missing>")):
        errors.append(f"Expected interpreter release of {expected_release} but was {release}.")
    if expected_version != (version := interpreter.get("version", "<missing>")):
        errors.append(f"Expected interpreter version of {expected_version} but was {version}.")
    if expected_flavor != (flavor := interpreter.get("flavor", "<missing>")):
        errors.append(f"Expected interpreter flavor of {expected_flavor} but was {flavor}.")
    if errors:
        return dedent(
            """
            Found the following lift.toml errors:
            {errors}

            Fix by aligning lift.toml noxfile.py values
            """
        ).format(errors=os.linesep.join(errors)).rstrip()

    return None

def main() -> Any:
    parser = ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--flavor", required=True)
    parser.add_argument("manifest", nargs=1, type=Path)
    options = parser.parse_args()
    return check_manifest(
        options.manifest[0],
        expected_release=options.release,
        expected_version=options.version,
        expected_flavor=options.flavor
    )


if __name__ == "__main__":
    sys.exit(main())
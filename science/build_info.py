# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from science import __version__
from science.hashing import Digest
from science.platform import Platform

logger = logging.getLogger(__name__)


def gather_build_info(lift_digest: Digest) -> dict[str, Any]:
    binary = dict[str, Any](
        version=__version__,
        url=(
            f"https://github.com/a-scie/lift/releases/tag/v{__version__}/"
            f"{Platform.current().qualified_binary_name('science')}"
        ),
    )
    if science := os.environ.get("SCIE_ARGV0"):
        digest = Digest.hash(Path(science))
        binary.update(size=digest.size, hash=digest.fingerprint)

    build_info = dict[str, Any](
        note=(
            "This scie lift JSON manifest was generated from a source lift toml manifest "
            "using the science binary."
        ),
        source_lift_toml=dict(size=lift_digest.size, hash=lift_digest.fingerprint),
        binary=binary,
    )

    if git := shutil.which("git"):
        git_info = subprocess.run(
            args=[git, "describe", "--always", "--dirty", "--long"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if git_info.returncode == 0:
            build_info.update(git_state=git_info.stdout.strip())
        else:
            logger.warning(f"Failed to gather git state for provenance.")
            logger.info(
                f"Got exit code {git_info.returncode} for command: {shlex.join(git_info.args)}"
            )
            logger.debug(f"Got STDERR:\n{git_info.stderr}")

    return build_info

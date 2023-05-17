# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from science import __version__
from science.frozendict import FrozenDict
from science.hashing import Digest
from science.platform import Platform

logger = logging.getLogger(__name__)


def _maybe_gather_git_state() -> str | None:
    git = shutil.which("git")
    if not git:
        return None

    git_info = subprocess.run(
        args=[git, "describe", "--always", "--dirty", "--long"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if git_info.returncode == 0:
        return git_info.stdout.strip()

    logger.warning(f"Failed to gather git state for provenance.")
    logger.info(f"Got exit code {git_info.returncode} for command: {shlex.join(git_info.args)}")
    logger.debug(f"Got STDERR:\n{git_info.stderr}")
    return None


@dataclass(frozen=True)
class Provenance:
    source: str
    digest: Digest | None = None


@dataclass(frozen=True)
class BuildInfo:
    @classmethod
    def gather(
        cls, lift_toml: Provenance, app_info: FrozenDict[str, Any] = FrozenDict()
    ) -> BuildInfo:
        digest = Digest.hash(Path(science)) if (science := os.environ.get("SCIE_ARGV0")) else None
        git_state = _maybe_gather_git_state()
        return cls(lift_toml, digest=digest, git_state=git_state, app_info=app_info)

    lift_toml: Provenance
    digest: Digest | None = None
    git_state: str | None = None
    app_info: FrozenDict[str, Any] = FrozenDict()

    def to_dict(self, **extra_app_info: Any) -> dict[str, Any]:
        binary = dict[str, Any](
            version=__version__,
            url=(
                f"https://github.com/a-scie/lift/releases/tag/v{__version__}/"
                f"{Platform.current().qualified_binary_name('science')}"
            ),
        )
        if self.digest:
            binary.update(size=self.digest.size, hash=self.digest.fingerprint)

        lift_toml = dict[str, Any](source=self.lift_toml.source)
        if self.lift_toml.digest:
            lift_toml.update(
                size=self.lift_toml.digest.size, hash=self.lift_toml.digest.fingerprint
            )

        build_info = dict[str, Any](
            notes=[
                "This scie lift JSON manifest was generated from a source lift toml manifest "
                "using the science binary.",
                f"Find out more here: https://github.com/a-scie/lift/blob/v{__version__}/README.md",
            ],
            binary=binary,
            manifest=lift_toml,
        )
        if self.git_state:
            build_info.update(git_state=self.git_state)

        app_info = {**self.app_info, **extra_app_info}
        if app_info:
            build_info.update(app_info=app_info)

        return build_info

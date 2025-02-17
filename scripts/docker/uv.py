# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os
import shutil
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from science.platform import CURRENT_OS, Os


def main() -> Any:
    if CURRENT_OS is Os.Windows:
        return "This script does not work on Windows yet."

    parser = ArgumentParser()
    parser.add_argument("--image", default="debian", choices=["alpine", "debian"])
    parser.add_argument(
        "--arch",
        default="amd64",
        choices=[
            "amd64",
            "arm64",
            "riscv64",
            "ppc64le",
            "s390x",
            "386",
            "mips64le",
            "mips64",
            "arm/v7",
            "arm/v6",
        ],
    )
    options, args = parser.parse_known_args()

    platform = f"linux/{options.arch}"
    subprocess.run(
        args=[
            "docker",
            "run",
            "--privileged",
            "--rm",
            "tonistiigi/binfmt",
            "--install",
            platform,
        ],
        check=True,
    )

    parent_dir = Path(__file__).parent
    arch_tag = options.arch.replace("/", "-")
    base_image = f"a-scie/lift/base:{arch_tag}"

    subprocess.run(
        args=[
            "docker",
            "buildx",
            "build",
            "--build-arg",
            f"UID={os.getuid()}",
            "--build-arg",
            f"GID={os.getgid()}",
            "--platform",
            platform,
            "--tag",
            base_image,
            str(parent_dir / options.image),
        ],
        check=True,
    )

    dev_image = f"a-scie/lift/dev:{arch_tag}"

    ephemeral_build_context = parent_dir / "ephemeral-build-context"
    ephemeral_build_context.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path("pyproject.toml"), ephemeral_build_context)
    shutil.copy(Path("uv.lock"), ephemeral_build_context)

    subprocess.run(
        args=[
            "docker",
            "buildx",
            "build",
            "--build-arg",
            f"BASE_IMAGE={base_image}",
            "--build-context",
            f"ephemeral={ephemeral_build_context}",
            "--platform",
            platform,
            "--tag",
            dev_image,
            str(parent_dir / "uv"),
        ],
        check=True,
    )

    subprocess.run(
        args=[
            "docker",
            "run",
            "-e",
            "FORCE_COLOR",
            "-e",
            "SCIENCE_AUTH_API_GITHUB_COM_BEARER",
            "-v",
            f"{Path().absolute()}:/code",
            "--platform",
            platform,
            dev_image,
            *args,
        ],
        check=True,
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        sys.exit(str(e))

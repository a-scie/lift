# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).
import hashlib
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

import coloredlogs

from science.platform import CURRENT_OS, Os

logger = logging.getLogger(__name__)


def fingerprint_path(path: Path) -> tuple[str, str]:
    if path.is_dir():
        tree: dict[str, str] = {}
        for r, _, files in os.walk(path):
            root = Path(r)
            for f in files:
                file_path = root / f
                tree[str(file_path.relative_to(path))] = hashlib.sha256(
                    file_path.read_bytes()
                ).hexdigest()

        fingerprint = hashlib.sha256(json.dumps(tree, sort_keys=True).encode()).hexdigest()
    else:
        fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()

    return str(path.resolve().relative_to(Path().resolve())), fingerprint


def fingerprint_paths(*paths: Path) -> str:
    return hashlib.sha256(
        json.dumps(dict(fingerprint_path(path) for path in paths), sort_keys=True).encode()
    ).hexdigest()


def image_exists(image_name: str) -> bool:
    result = subprocess.run(
        args=["docker", "image", "ls", "-q", image_name], capture_output=True, text=True
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def main() -> Any:
    if CURRENT_OS is Os.Windows:
        return "This script does not work on Windows yet."

    coloredlogs.install(
        fmt="%(levelname)s %(message)s",
        field_styles={
            **coloredlogs.DEFAULT_FIELD_STYLES,
            # Default is bold black, we switch to gray; c.f:
            # https://coloredlogs.readthedocs.io/en/latest/api.html#available-text-styles-and-colors
            "levelname": {"bold": True, "color": 8},
        },
    )

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
    parser.add_argument(
        "--inspect",
        default=False,
        action="store_true",
        help="Instead of running `uv run dev-cmd` against the extra args, drop into a shell in the image for inspection.",
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

    dev_image_context = parent_dir / "uv"
    fingerprint = fingerprint_paths(Path("pyproject.toml"), Path("uv.lock"), dev_image_context)
    dev_image = f"a-scie/lift/dev:{options.image}-{arch_tag}-{fingerprint}"
    if not image_exists(dev_image):
        base_image_context = parent_dir / options.image
        fingerprint = fingerprint_paths(base_image_context)
        base_image = f"a-scie/lift/base:{options.image}-{arch_tag}-{fingerprint}"
        if not image_exists(base_image):
            # The type-ignores for os.get{uid,gid} cover Windows which we explicitly fail-fast for above.
            subprocess.run(
                args=[
                    "docker",
                    "buildx",
                    "build",
                    "--build-arg",
                    f"UID={os.getuid()}",  # type:ignore[attr-defined]
                    "--build-arg",
                    f"GID={os.getgid()}",  # type:ignore[attr-defined]
                    "--platform",
                    platform,
                    "--tag",
                    base_image,
                    str(base_image_context),
                ],
                check=True,
            )

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
                str(dev_image_context),
            ],
            check=True,
        )

    docker_run_args = [
        "docker",
        "run",
        "--rm",
        "-e",
        "FORCE_COLOR",
        "-e",
        "SCIENCE_AUTH_API_GITHUB_COM_BEARER",
        "-v",
        f"{Path().absolute()}:/code",
        "--platform",
        platform,
    ]
    if options.inspect:
        if args:
            logger.warning(f"Ignoring extra args in --inspect mode: {shlex.join(args)}")
        docker_run_args.append("--interactive")
        docker_run_args.append("--tty")
        docker_run_args.append("--entrypoint")
        docker_run_args.append("sh" if options.image == "alpine" else "bash")
        docker_run_args.append(dev_image)
        docker_run_args.append("-i")
    else:
        docker_run_args.append(dev_image)
        docker_run_args.extend(args)

    subprocess.run(args=docker_run_args, check=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        sys.exit(str(e))

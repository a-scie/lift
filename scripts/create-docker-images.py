# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).
import atexit
import os
import shutil
import subprocess
import sys
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from pathlib import Path, PurePath
from subprocess import CalledProcessError
from tempfile import mkdtemp
from textwrap import dedent
from typing import Any, Iterable

import colors
import yaml


def read_required_platforms():
    with (Path(".github") / "workflows" / "ci.yml").open() as fp:
        data = yaml.full_load(fp)
    platforms = sorted(
        set(
            entry["docker-platform"]
            for entry in data["jobs"]["ci"]["strategy"]["matrix"]["include"]
            if "docker-platform" in entry
        )
    )
    return platforms


def export_requirements() -> PurePath:
    requirements_dir = Path(mkdtemp())
    atexit.register(shutil.rmtree, requirements_dir, ignore_errors=True)

    requirements_txt = requirements_dir / "requirements.txt"
    subprocess.run(
        args=["uv", "export", "--no-hashes", "--no-emit-project", "-o", requirements_txt],
        check=True,
    )
    return requirements_txt


def ensure_binfmts_installed() -> None:
    subprocess.run(
        args=["docker", "run", "--privileged", "--rm", "tonistiigi/binfmt", "--install", "all"],
        check=True,
    )


def obtain_wheels(
    base_image: str,
    platforms: Iterable[str],
    requirements_txt: PurePath,
    wheel_dir: Path,
    clean: bool,
    skip_build: bool,
) -> None:
    if clean:
        subprocess.run(args=["docker", "volume", "rm", "--force", "science-wheels"], check=True)
    subprocess.run(args=["docker", "volume", "create", "science-wheels"], check=True)
    for platform in platforms:
        if not skip_build:
            print(colors.color(f"Building wheels for {platform}...", fg="gray"), file=sys.stderr)
            subprocess.run(
                args=[
                    "docker",
                    "run",
                    "--rm",
                    "--platform",
                    platform,
                    "--volume",
                    "science-wheels:/wheels",
                    "--volume",
                    f"{requirements_txt}:/requirements.txt",
                    base_image,
                    "pip",
                    "wheel",
                    "-f",
                    "/wheels",
                    "-r",
                    "/requirements.txt",
                    "-w",
                    "/wheels",
                ],
                check=True,
            )
        print(
            colors.color(f"Saving wheels for {platform} to {wheel_dir}...", fg="gray"),
            file=sys.stderr,
        )
        subprocess.run(
            args=[
                "docker",
                "run",
                "--rm",
                "--volume",
                "science-wheels:/wheels",
                "--volume",
                f"{wheel_dir.absolute()}:/mnt/wheels",
                "busybox",
                "sh",
                "-c",
                dedent(
                    f"""\
                    cp /wheels/*.whl /mnt/wheels
                    chown -R {os.getuid()}:{os.getgid()} /mnt/wheels
                    chmod 755 /mnt/wheels
                    """
                ),
            ],
            check=True,
        )


def create_docker_image(
    base_image: str, tag: str, platforms: Iterable[str], wheel_dir: PurePath, push: bool
) -> None:
    context = PurePath("docker")
    image_tag = f"ghcr.io/a-scie/lift/dev:{tag}"
    subprocess.run(
        args=[
            "docker",
            "buildx",
            "build",
            "--build-arg",
            f"SRC_WHEEL_DIR={wheel_dir.relative_to(context)}",
            "--build-arg",
            f"BASE_IMAGE={base_image}",
            "--platform",
            ",".join(platforms),
            "--tag",
            image_tag,
            context,
        ],
        check=True,
    )

    if push:
        subprocess.run(args=["docker", "push", image_tag], check=True)


def main() -> Any:
    parser = ArgumentParser(
        formatter_class=ArgumentDefaultsHelpFormatter,
        description=(
            "Builds (and optionally pushes) a development image for all Linux platforms supported "
            "by science."
        ),
    )
    parser.add_argument(
        "--base-image",
        default="python:3.12-bookworm",
        help="The base image to use.",
    )
    parser.add_argument(
        "--tag",
        default="latest",
        help="The tag for the ghcr.io/a-scie/lift/dev image.",
    )
    parser.add_argument(
        "--clean",
        default=False,
        action="store_true",
        help="Do a fresh set of wheel builds.",
    )
    parser.add_argument(
        "--skip-build",
        default=False,
        action="store_true",
        help="Skip wheel builds.",
    )
    parser.add_argument(
        "--push",
        default=False,
        action="store_true",
        help="Push the image to the registry after building and tagging it.",
    )
    options = parser.parse_args()

    platforms = read_required_platforms()
    requirements_txt = export_requirements()

    ensure_binfmts_installed()

    wheel_dir = Path("docker") / "ephemeral-context" / "wheels"
    shutil.rmtree(wheel_dir, ignore_errors=True)
    wheel_dir.mkdir(parents=True, exist_ok=True)
    obtain_wheels(
        options.base_image,
        platforms,
        requirements_txt,
        wheel_dir,
        clean=options.clean,
        skip_build=options.skip_build,
    )
    return create_docker_image(options.base_image, options.tag, platforms, wheel_dir, options.push)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CalledProcessError as e:
        sys.exit(colors.red(str(e)))

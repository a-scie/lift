# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import atexit
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    work_dir = Path(tempfile.mkdtemp(prefix="science-zipapp-build."))
    atexit.register(shutil.rmtree, work_dir, ignore_errors=True)

    locked_requirements = work_dir / "requirements.txt"
    wheels = work_dir / "wheels"
    processes = [
        subprocess.Popen(
            args=["uv", "-q", "export", "--no-dev", "--no-emit-project", "-o", locked_requirements],
        ),
        subprocess.Popen(args=["uv", "-q", "build", "--wheel", "-o", wheels]),
    ]
    while processes:
        process = processes.pop()
        exit_code = process.wait()
        if 0 != exit_code:
            for maybe_in_flight_process in processes:
                maybe_in_flight_process.terminate()
            return exit_code

    site_packages_dir = work_dir / "site-packages"
    if 0 != (
        exit_code := subprocess.call(
            args=[
                "uv",
                "-q",
                "pip",
                "install",
                "--target",
                site_packages_dir,
                "--requirements",
                locked_requirements,
                *wheels.glob("*.whl"),
            ]
        )
    ):
        return exit_code

    # Science runs in a scie that carries its own interpreter; so pins to a single major/minor for
    # development that matches prod; as such, we can just take the ambient interpreter major/minor
    # and know it matches the project Requires-Python.
    python = f"python{sys.version_info[0]}.{sys.version_info[1]}"

    dest = Path("dist") / "science.pyz"
    dest.parent.mkdir(exist_ok=True)
    dest.unlink(missing_ok=True)
    return subprocess.call(
        args=[
            "shiv",
            "-p",
            f"/usr/bin/env {python}",
            "-c",
            "science",
            "--site-packages",
            site_packages_dir,
            "--reproducible",
            "-o",
            dest,
        ],
    )


if __name__ == "__main__":
    sys.exit(main())

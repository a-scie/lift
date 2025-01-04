# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def main() -> Any:
    work_dir = Path(tempfile.mkdtemp())
    site_packages_dir = work_dir / "site-packages"
    locked_requirements = work_dir / "requirements.txt"

    subprocess.run(
        args=["uv", "-q", "export", "--no-editable", "--no-dev", "-o", locked_requirements],
        check=True,
    )
    subprocess.run(
        args=[
            "uv",
            "-q",
            "pip",
            "install",
            "--target",
            site_packages_dir,
            "--requirements",
            locked_requirements,
        ],
        check=True,
    )

    # Science runs in a scie that carries its own interpreter; so pins to a single major/minor for
    # development that matches prod; as such, we can just take the ambient interpreter major/minor
    # and know it matches the project Requires-Python.
    python = f"python{sys.version_info[0]}.{sys.version_info[1]}"

    dest = Path("dist") / "science.pyz"
    dest.parent.mkdir(exist_ok=True)
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

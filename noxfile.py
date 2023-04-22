# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from functools import wraps
from pathlib import Path
from typing import Callable, Iterable, TypeVar

import nox
from nox import Session

nox.needs_version = ">=2022.11.21"

BUILD_ROOT = Path().resolve()
DIST_DIR = BUILD_ROOT / "dist"
NOX_SUPPORT_DIR = BUILD_ROOT / "nox-support"

REQUIRES_PYTHON_VERSION = "3.11"
PATHS_TO_CHECK = ["science", "tests", "noxfile.py"]

T = TypeVar("T")


def nox_session() -> Callable[[Callable[[Session], T]], Callable[[Session], T]]:
    return nox.session(python=[REQUIRES_PYTHON_VERSION], reuse_venv=True)


def python_session(
    include_project: bool = False,
    extra_reqs: Iterable[str] = (),
) -> Callable[[Callable[[Session], T]], Callable[[Session], T]]:
    def wrapped(func: Callable[[Session], T]) -> Callable[[Session], T]:
        @wraps(func)
        def wrapper(session: Session) -> T:
            for req in (func.__name__, *extra_reqs):
                session.install("-r", str(NOX_SUPPORT_DIR / f"{req}-reqs.txt"))
            if include_project:
                session.install("-r", "requirements.txt")
                session.install("-e", ".")
            return func(session)

        return nox_session()(wrapper)

    return wrapped


def run_black(session: Session, *args: str) -> None:
    session.run("black", "--color", *PATHS_TO_CHECK, *args, *session.posargs)


def run_isort(session: Session, *args: str) -> None:
    session.run("isort", *PATHS_TO_CHECK, *args, *session.posargs)


def run_autoflake(session: Session, *args: str) -> None:
    session.run("autoflake", "--quiet", "--recursive", *PATHS_TO_CHECK, *args, *session.posargs)


@python_session()
def fmt(session: Session) -> None:
    run_black(session)
    run_isort(session)
    run_autoflake(session, "--remove-all-unused-imports", "--in-place")


@python_session()
def lint(session: Session) -> None:
    run_black(session, "--check")
    run_isort(session, "--check-only")
    run_autoflake(session, "--check")


@python_session(include_project=True, extra_reqs=["test"])
def check(session: Session) -> None:
    session.run(
        "mypy", "--python-version", REQUIRES_PYTHON_VERSION, *PATHS_TO_CHECK, *session.posargs
    )


PACKAGED: Path | None = None


def create_zipapp(session: Session) -> Path:
    global PACKAGED
    if PACKAGED is None:
        DIST_DIR.mkdir(parents=True, exist_ok=True)
        dest = DIST_DIR / "science.pyz"
        session.run(
            "shiv",
            "-p",
            f"/usr/bin/env python{REQUIRES_PYTHON_VERSION}",
            "-c",
            "science",
            ".",
            "--reproducible",
            "-o",
            str(dest),
        )
        PACKAGED = dest.resolve()
    return PACKAGED


@nox_session()
def test(session: Session) -> None:
    science_pyz = create_zipapp(session)
    test_env = {"BUILD_ROOT": str(BUILD_ROOT), "SCIENCE_TEST_PYZ_PATH": str(science_pyz)}
    session.run("pytest", *session.posargs, env=test_env)


@python_session()
def package(session: Session) -> None:
    science_pyz = create_zipapp(session)
    session.run(
        "python",
        str(science_pyz),
        "build",
        "--file",
        f"science.pyz={science_pyz}",
        "--dest-dir",
        str(DIST_DIR),
        str(BUILD_ROOT / "science.toml"),
    )

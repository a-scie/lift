# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import hashlib
import itertools
from functools import wraps
from pathlib import Path
from typing import Callable, Collection, Iterable, TypeVar

import nox
from nox import Session

nox.needs_version = ">=2022.11.21"

REQUIRES_PYTHON_VERSION = "3.11"
# PEX_REQUIREMENT = "pex==2.1.134"
PEX_REQUIREMENT = (
    "pex @ git+https://github.com/jsirois/pex@59b19235aa50424b9ac5e6ac298e4b5f4aeb4afb"
)
PEX_PEX = f"pex-{hashlib.sha1(PEX_REQUIREMENT.encode('utf-8')).hexdigest()}.pex"

BUILD_ROOT = Path().resolve()
LOCK_IN = BUILD_ROOT / "lock.in"
LOCK_FILE = BUILD_ROOT / "lock.json"


def run_pex(session: Session, script, *args, **env) -> None:
    pex_pex = session.cache_dir / PEX_PEX
    if not pex_pex.exists():
        session.install(PEX_REQUIREMENT)
        session.run("pex", PEX_REQUIREMENT, "--venv", "--sh-boot", "-o", str(pex_pex))
        session.run("python", "-m", "pip", "uninstall", "-y", "pex")
    session.run("python", str(pex_pex), *args, env={"PEX_SCRIPT": script, **env})


def maybe_create_lock(session: Session) -> bool:
    if LOCK_FILE.exists():
        return False

    run_pex(
        session,
        "pex3",
        "lock",
        "create",
        "-r",
        str(LOCK_IN),
        "--interpreter-constraint",
        f"=={REQUIRES_PYTHON_VERSION}.*",
        "--style",
        "universal",
        "--pip-version",
        "latest",
        "--resolver-version",
        "pip-2020-resolver",
        "--indent",
        "2",
        "-o",
        str(LOCK_FILE),
    )
    return True


def install_locked_requirements(session: Session, input_reqs: Iterable[Path]) -> None:
    maybe_create_lock(session)

    run_pex(
        session,
        "pex3",
        "lock",
        "venv",
        "-d",
        session.virtualenv.location,
        "--lock",
        str(LOCK_FILE),
        *itertools.chain.from_iterable(("-r", str(req_file)) for req_file in input_reqs),
    )


T = TypeVar("T")


def nox_session() -> Callable[[Callable[[Session], T]], Callable[[Session], T]]:
    return nox.session(python=[REQUIRES_PYTHON_VERSION], reuse_venv=True)


@nox_session()
def lock(session: Session) -> None:
    if not maybe_create_lock(session):
        session.warn("Not updating lock files. Remove them to force updates.")


NOX_SUPPORT_DIR = BUILD_ROOT / "nox-support"


def python_session(
    include_project: bool = False,
    extra_reqs: Collection[str] = (),
) -> Callable[[Callable[[Session], T]], Callable[[Session], T]]:
    def wrapped(func: Callable[[Session], T]) -> Callable[[Session], T]:
        @wraps(func)
        def wrapper(session: Session) -> T:
            requirements = []
            for req in (func.__name__, *extra_reqs):
                session_reqs = NOX_SUPPORT_DIR / f"{req}-reqs.txt"
                if req in extra_reqs or session_reqs.is_file():
                    requirements.append(session_reqs)
            if include_project:
                requirements.append(BUILD_ROOT / "requirements.txt")

            install_locked_requirements(session, input_reqs=requirements)
            return func(session)

        return nox_session()(wrapper)

    return wrapped


PATHS_TO_CHECK = ["science", "tests", "noxfile.py"]


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


@python_session(extra_reqs=["fmt"])
def lint(session: Session) -> None:
    run_black(session, "--check")
    run_isort(session, "--check-only")
    run_autoflake(session, "--check")


@python_session(include_project=True, extra_reqs=["test"])
def check(session: Session) -> None:
    session.run(
        "mypy", "--python-version", REQUIRES_PYTHON_VERSION, *PATHS_TO_CHECK, *session.posargs
    )


DIST_DIR = BUILD_ROOT / "dist"
PACKAGED: Path | None = None


def create_zipapp(session: Session) -> Path:
    global PACKAGED
    if PACKAGED is None:
        venv_dir = Path(session.create_tmp()) / "science"
        run_pex(
            session,
            "pex3",
            "lock",
            "venv",
            "--force",
            "-d",
            str(venv_dir),
            "-r",
            str(BUILD_ROOT / "requirements.txt"),
            "--lock",
            str(LOCK_FILE),
        )

        site_packages = venv_dir / "lib" / f"python{REQUIRES_PYTHON_VERSION}" / "site-packages"
        if not site_packages.is_dir():
            session.error(f"Failed to find site-packages directory in venv at {venv_dir}")

        session.run("python", "-m", "pip", "install", "--prefix", str(venv_dir), "--no-deps", ".")

        DIST_DIR.mkdir(parents=True, exist_ok=True)
        dest = DIST_DIR / "science.pyz"
        session.run(
            "shiv",
            "-p",
            f"/usr/bin/env python{REQUIRES_PYTHON_VERSION}",
            "-c",
            "science",
            "--site-packages",
            str(site_packages),
            "--reproducible",
            "-o",
            str(dest),
        )
        PACKAGED = dest.resolve()
    return PACKAGED


@python_session(include_project=True, extra_reqs=["package"])
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

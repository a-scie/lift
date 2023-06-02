# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import glob
import hashlib
import itertools
import json
import os
import shutil
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Collection, Iterable, TypeVar, cast

import nox
from nox import Session

nox.needs_version = ">=2022.11.21"
nox.options.stop_on_first_error = True
nox.options.sessions = ["fmt", "lint", "check", "test"]

REQUIRES_PYTHON_VERSION = "3.11"

PEX_REQUIREMENT = "pex==2.1.136"
PEX_PEX = f"pex-{hashlib.sha1(PEX_REQUIREMENT.encode('utf-8')).hexdigest()}.pex"

BUILD_ROOT = Path().resolve()
WINDOWS_AMD64_COMPLETE_PLATFORM = BUILD_ROOT / "complete-platform.windows-amd64-py3.11.json"
LOCK_FILE = BUILD_ROOT / "lock.json"

IS_WINDOWS = os.name == "nt"


def run_pex(session: Session, script, *args, silent=False, **env) -> Any | None:
    pex_pex = session.cache_dir / PEX_PEX
    if not pex_pex.exists():
        session.install(PEX_REQUIREMENT)
        session.run("pex", PEX_REQUIREMENT, "--venv", "--sh-boot", "-o", str(pex_pex))
        session.run("python", "-m", "pip", "uninstall", "-y", "pex")
    return session.run(
        "python", str(pex_pex), *args, env={"PEX_SCRIPT": script, **env}, silent=silent
    )


def maybe_create_lock(session: Session) -> bool:
    all_requirements = [BUILD_ROOT / "requirements.txt"] + [
        Path(p) for p in glob.glob(str(BUILD_ROOT / "nox-support" / "*-reqs.txt"))
    ]
    created_lock = False
    if not LOCK_FILE.exists():
        run_pex(
            session,
            "pex3",
            "lock",
            "create",
            *itertools.chain.from_iterable(("-r", str(req)) for req in all_requirements),
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
        created_lock = True

    for subset in all_requirements:
        subset_lock = subset.with_suffix(".windows-amd64.lock.txt")
        if not created_lock and subset_lock.exists():
            continue
        run_pex(
            session,
            "pex3",
            "lock",
            "export-subset",
            "--lock",
            str(LOCK_FILE),
            "-r",
            str(subset),
            "--complete-platform",
            str(WINDOWS_AMD64_COMPLETE_PLATFORM),
            "-o",
            str(subset_lock),
        )

    return created_lock


def install_locked_requirements(session: Session, input_reqs: Iterable[Path]) -> None:
    maybe_create_lock(session)

    if IS_WINDOWS:
        # N.B: We avoid this installation technique when not on Windows since it's a good deal
        # slower than using Pex.
        session.install(
            *itertools.chain.from_iterable(
                ("-r", str(req_file.with_suffix(".windows-amd64.lock.txt")))
                for req_file in input_reqs
            )
        )
    else:
        run_pex(
            session,
            "pex3",
            "venv",
            "create",
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
        session.warn(
            f"Not updating lock file. Remove {LOCK_FILE.relative_to(BUILD_ROOT)} to force updates."
        )


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


PATHS_TO_CHECK = ["science", "tests", "test-support", "noxfile.py", "docs"]


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


@python_session(include_project=True, extra_reqs=["doc", "test"])
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
        if IS_WINDOWS:
            session.run("python", "-m", "venv", str(venv_dir))
            session.run(
                str(venv_dir / "Scripts" / "python.exe"),
                "-m",
                "pip",
                "install",
                "-r",
                str(BUILD_ROOT / "requirements.windows-amd64.lock.txt"),
                external=True,
            )
            site_packages = str(venv_dir / "Lib" / "site-packages")
        else:
            run_pex(
                session,
                "pex3",
                "venv",
                "create",
                "--force",
                "-d",
                str(venv_dir),
                "-r",
                str(BUILD_ROOT / "requirements.txt"),
                "--lock",
                str(LOCK_FILE),
            )
            site_packages = json.loads(
                cast(str, run_pex(session, "pex3", "venv", "inspect", str(venv_dir), silent=True))
            )["site_packages"]

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
    session.run("pytest", "-n" "auto", *(session.posargs or ["-v"]), env=test_env)


@python_session(include_project=True)
def doc(session: Session) -> None:
    gen_doc_type = "html"
    docs_dir = BUILD_ROOT / "docs"
    build_dir = docs_dir / "build" / gen_doc_type
    shutil.rmtree(build_dir, ignore_errors=True)
    session.run("sphinx-build", "-b", gen_doc_type, "-aEW", str(docs_dir), str(build_dir))


@python_session()
def run(session: Session) -> None:
    science_pyz = create_zipapp(session)
    session.run("python", str(science_pyz), *session.posargs)


def _package(session: Session, *extra_lift_args: str) -> None:
    science_pyz = create_zipapp(session)
    session.run(
        "python",
        str(science_pyz),
        "lift",
        "--file",
        f"science.pyz={science_pyz}",
        "--include-provenance",
        *extra_lift_args,
        "build",
        "--hash",
        "sha256",
        "--use-platform-suffix",
        env={
            "SCIENCE_LIFT_BUILD_DEST_DIR": os.environ.get(
                "SCIENCE_LIFT_BUILD_DEST_DIR", str(DIST_DIR)
            )
        },
    )


@python_session()
def package(session: Session) -> None:
    _package(session)
    _package(session, "--invert-lazy", "cpython", "--app-name", "science-fat")

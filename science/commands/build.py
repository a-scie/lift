# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import dataclasses
import hashlib
import io
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from science import a_scie
from science.commands import lift
from science.commands.lift import LiftConfig, PlatformInfo
from science.fs import temporary_directory
from science.model import Application
from science.platform import CURRENT_PLATFORM, CURRENT_PLATFORM_SPEC, PlatformSpec


@dataclass(frozen=True)
class ScieAssembly:
    lift_manifest: Path
    scie: Path
    hashes: tuple[Path, ...]


@dataclass(frozen=True)
class AssemblyInfo:
    native_jump: Path
    scies: tuple[ScieAssembly, ...]


def _native_jump(
    application: Application, platform_specs: tuple[PlatformSpec, ...]
) -> a_scie.LoadResult:
    # The native scie-jump assembles each scie, so it comes from the same release and mirror as the
    # scie-jump each scie embeds. A configured digest is that of one platform's binary, so it only
    # applies when that platform is the only one and is the current one.
    specification = application.scie_jump
    if specification and specification.digest and platform_specs != (CURRENT_PLATFORM_SPEC,):
        specification = dataclasses.replace(specification, digest=None)
    return a_scie.jump(specification=specification)


def assemble_scies(
    lift_config: LiftConfig,
    application: Application,
    dest_dir: Path,
    platform_specs: Iterable[PlatformSpec],
    platform_info: PlatformInfo,
    use_jump: Path | None,
    hash_functions: list[str],
) -> AssemblyInfo:
    specs = tuple(platform_specs) or tuple(application.platform_specs)
    native_jump_path = (
        a_scie.custom_jump(path=use_jump) if use_jump else _native_jump(application, specs)
    ).path

    scies = list[ScieAssembly]()
    for platform_spec, lift_manifest, jump_path, _ in lift.export_manifest(
        lift_config,
        application,
        dest_dir=dest_dir,
        platform_specs=specs,
        use_jump=use_jump,
    ):
        with temporary_directory("assemble") as build_dir:
            subprocess.run(
                args=[str(native_jump_path), "-sj", str(jump_path), lift_manifest],
                cwd=build_dir,
                stdout=subprocess.DEVNULL,
                check=True,
            )

            src_binary = Path(build_dir) / CURRENT_PLATFORM.binary_name(application.name)
            dst_binary_name = platform_info.binary_name(
                application.name, target_platform=platform_spec
            )
            dst_binary = dest_dir / dst_binary_name
            shutil.move(src_binary, dst_binary)

        hashes = list[Path]()
        if hash_functions:
            digests = tuple(
                hashlib.new(hash_function) for hash_function in sorted(set(hash_functions))
            )
            with dst_binary.open(mode="rb") as fp:
                for chunk in iter(lambda: fp.read(io.DEFAULT_BUFFER_SIZE), b""):
                    for digest in digests:
                        digest.update(chunk)
            for digest in digests:
                checksum_file = dst_binary.with_name(f"{dst_binary_name}.{digest.name}")
                checksum_file.write_text(f"{digest.hexdigest()} *{dst_binary_name}")
                hashes.append(checksum_file)
        scies.append(
            ScieAssembly(lift_manifest=lift_manifest, scie=dst_binary, hashes=tuple(hashes))
        )

    return AssemblyInfo(native_jump=native_jump_path, scies=tuple(scies))

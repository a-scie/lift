# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

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
from science.platform import CURRENT_PLATFORM, PlatformSpec


@dataclass(frozen=True)
class ScieAssembly:
    lift_manifest: Path
    scie: Path
    hashes: tuple[Path, ...]


@dataclass(frozen=True)
class AssemblyInfo:
    native_jump: Path
    scies: tuple[ScieAssembly, ...]


def assemble_scies(
    lift_config: LiftConfig,
    application: Application,
    dest_dir: Path,
    platform_specs: Iterable[PlatformSpec],
    platform_info: PlatformInfo,
    use_jump: Path | None,
    hash_functions: list[str],
) -> AssemblyInfo:
    native_jump_path = (a_scie.custom_jump(repo_path=use_jump) if use_jump else a_scie.jump()).path

    scies = list[ScieAssembly]()
    for platform_spec, lift_manifest in lift.export_manifest(
        lift_config, application, dest_dir=dest_dir, platform_specs=platform_specs
    ):
        jump_path = (
            a_scie.custom_jump(repo_path=use_jump)
            if use_jump
            else a_scie.jump(specification=application.scie_jump, platform=platform_spec.platform)
        ).path
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

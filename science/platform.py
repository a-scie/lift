# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import os
import platform
import subprocess
import sys
from enum import Enum
from functools import cache, cached_property

from science.dataclass.reflect import documented_dataclass
from science.errors import InputError


class Os(Enum):
    Linux = "linux"
    Macos = "macos"
    Windows = "windows"

    @classmethod
    def current(cls) -> Os:
        match platform.system().lower():
            case "linux":
                return cls.Linux
            case "darwin":
                return cls.Macos
            case "windows":
                return cls.Windows
            case system:
                raise InputError(f"The current operating system is not supported!: {system}")

    def __str__(self) -> str:
        return self.value


CURRENT_OS = Os.current()


class Arch(Enum):
    ARM64 = "aarch64"
    ARMv7l = "armv7l"
    PPC64le = "powerpc64"
    S390X = "s390x"
    X86_64 = "x86_64"

    def __str__(self) -> str:
        return self.value


class OsArch:
    def __init__(self, os_: Os, arch: Arch):
        self.os = os_
        self.arch = arch

    @cached_property
    def value(self) -> str:
        return f"{self.os.value}-{self.arch.value}"

    @property
    def is_windows(self) -> bool:
        return self.os is Os.Windows

    @property
    def extension(self):
        return ".exe" if self.is_windows else ""

    def join_path(self, *components: str) -> str:
        return ("\\" if self.is_windows else "/").join(components)

    def binary_name(self, binary_name: str) -> str:
        return f"{binary_name}{self.extension}"

    def qualified_binary_name(self, binary_name: str, *extra_qualifiers: str) -> str:
        return f"{binary_name}-{'-'.join((*extra_qualifiers, self.value))}{self.extension}"

    def __str__(self) -> str:
        return self.value


class Platform(OsArch, Enum):
    Linux_aarch64 = Os.Linux, Arch.ARM64
    Linux_armv7l = Os.Linux, Arch.ARMv7l
    Linux_powerpc64le = Os.Linux, Arch.PPC64le
    Linux_s390x = Os.Linux, Arch.S390X
    Linux_x86_64 = Os.Linux, Arch.X86_64
    Macos_aarch64 = Os.Macos, Arch.ARM64
    Macos_x86_64 = Os.Macos, Arch.X86_64
    Windows_aarch64 = Os.Windows, Arch.ARM64
    Windows_x86_64 = Os.Windows, Arch.X86_64

    @classmethod
    @cache
    def parse(cls, value: str) -> Platform:
        if "current" == value:
            return CURRENT_PLATFORM

        known_values: list[str] = []
        for plat in cls:
            if value == plat.value:
                return plat
            known_values.append(plat.value)

        raise InputError(
            f"Invalid platform string {value!r}.{os.linesep}"
            f"Known values are:{os.linesep}"
            f"{os.linesep.join(f'+ {v}' for v in known_values)}"
        )

    @classmethod
    def current(cls) -> Platform:
        # N.B.: Used by the science scie to seal in the correct current platform as determined by
        # the scie-jump. This helps work around our Windows ARM64 science binary thinking its
        # running on Windows x86-64 since we use an x86-64 PBS Cpython in that scie.
        if current := os.environ.get("__SCIENCE_CURRENT_PLATFORM__"):
            return cls.parse(current)

        match (system := CURRENT_OS, machine := platform.machine().lower()):
            case (Os.Linux, "aarch64" | "arm64"):
                return cls.Linux_aarch64
            case (Os.Linux, "armv7l" | "armv8l"):
                return cls.Linux_armv7l
            case (Os.Linux, "ppc64le"):
                return cls.Linux_powerpc64le
            case (Os.Linux, "s390x"):
                return cls.Linux_s390x
            case (Os.Linux, "amd64" | "x86_64"):
                return cls.Linux_x86_64
            case (Os.Macos, "aarch64" | "arm64"):
                return cls.Macos_aarch64
            case (Os.Macos, "amd64" | "x86_64"):
                return cls.Macos_x86_64
            case (Os.Windows, "aarch64" | "arm64"):
                return cls.Windows_aarch64
            case (Os.Windows, "amd64" | "x86_64"):
                return cls.Windows_x86_64
            case _:
                raise InputError(
                    "The current operating system / machine pair is not supported!: "
                    f"{system} / {machine}"
                )


CURRENT_PLATFORM = Platform.current()


class LibC(Enum):
    @classmethod
    @cache
    def current(cls) -> LibC | None:
        if CURRENT_PLATFORM.os is not Os.Linux or CURRENT_PLATFORM.arch is not Arch.X86_64:
            return None
        if (
            "musl"
            in subprocess.run(
                args=["ldd", sys.executable],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            ).stdout
        ):
            return LibC.MUSL
        return LibC.GLIBC

    GLIBC = "gnu"
    MUSL = "musl"

    def __str__(self) -> str:
        return self.value


@documented_dataclass(frozen=True, alias="platform specification")
class PlatformSpec:
    """A specification of a platform a scie targets.

    A platform specification at its most basic is a string identifying the operating system /
    processor architecture pair, a.k.a. the platform; e.g.: `"linux-x86_64"`.

    For some systems more detail is needed to distinguish between available software ecosystems and
    additional available hardware details. If you need to pick out this level of detail, instead of
    supplying a platform string, supply a table with a platform string entry and any other entries
    needed to narrow down the platform specification. For example, to specify a musl Linux system
    you might use: `{platform = "linux-x86_64", libc = "musl"}`.

    You are free to mix simple platform strings with platform specification tables as values in
    arrays and tables that accept platform specification values. For example, this is a valid list
    of lift platforms to target in a lift manifest:
    ```toml
    [lift]
    platforms = [
        "linux-aarch64",
        {platform = "linux-x86_64", libc = "glibc"},
        {platform = "linux-x86_64", libc = "musl"},
        "macos-aarch64",
        "macos-x86_64",
    ]
    ```
    """

    platform: Platform
    libc: LibC | None = None

    def binary_name(self, binary_name: str) -> str:
        return self.platform.binary_name(binary_name)

    def qualified_binary_name(self, binary_name: str) -> str:
        if LibC.MUSL is self.libc:
            return self.platform.qualified_binary_name(binary_name, self.libc.value)
        return self.platform.qualified_binary_name(binary_name)

    @property
    def value(self) -> str:
        if self.libc is LibC.MUSL:
            return f"{self.platform.value}-{self.libc.value}"
        return self.platform.value

    @property
    def is_windows(self) -> bool:
        return self.platform.is_windows

    def join_path(self, *components: str) -> str:
        return self.platform.join_path(*components)

    def __repr__(self) -> str:
        if self.libc:
            return f"""{{platform = "{self.platform}", libc = "{self.libc}"}}"""
        return self.platform.value


CURRENT_PLATFORM_SPEC = PlatformSpec(CURRENT_PLATFORM, libc=LibC.current())

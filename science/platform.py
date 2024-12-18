# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import os
import platform
from enum import Enum

from science.errors import InputError


class Platform(Enum):
    Linux_aarch64 = "linux-aarch64"
    Linux_armv7l = "linux-armv7l"
    Linux_powerpc64le = "linux-powerpc64"
    Linux_s390x = "linux-s390x"
    Linux_x86_64 = "linux-x86_64"
    Macos_aarch64 = "macos-aarch64"
    Macos_x86_64 = "macos-x86_64"
    Windows_aarch64 = "windows-aarch64"
    Windows_x86_64 = "windows-x86_64"

    @classmethod
    def parse(cls, value: str) -> Platform:
        return Platform.current() if "current" == value else Platform(value)

    @classmethod
    def current(cls) -> Platform:
        # N.B.: Used by the science scie to seal in the correct current platform as determined by
        # the scie-jump. This helps work around our Windows ARM64 science binary thinking its
        # running on Windows x86-64 since we use an x86-64 PBS Cpython in that scie.
        if current := os.environ.get("__SCIENCE_CURRENT_PLATFORM__"):
            return cls.parse(current)

        match (system := platform.system().lower(), machine := platform.machine().lower()):
            case ("linux", "aarch64" | "arm64"):
                return cls.Linux_aarch64
            case ("linux", "armv7l" | "armv8l"):
                return cls.Linux_armv7l
            case ("linux", "ppc64le"):
                return cls.Linux_powerpc64le
            case ("linux", "s390x"):
                return cls.Linux_s390x
            case ("linux", "amd64" | "x86_64"):
                return cls.Linux_x86_64
            case ("darwin", "aarch64" | "arm64"):
                return cls.Macos_aarch64
            case ("darwin", "amd64" | "x86_64"):
                return cls.Macos_x86_64
            case ("windows", "aarch64" | "arm64"):
                return cls.Windows_aarch64
            case ("windows", "amd64" | "x86_64"):
                return cls.Windows_x86_64
            case _:
                raise InputError(
                    "The current operating system / machine pair is not supported!: "
                    f"{system} / {machine}"
                )

    @property
    def extension(self):
        return ".exe" if self in (self.Windows_aarch64, self.Windows_x86_64) else ""

    def binary_name(self, binary_name: str) -> str:
        return f"{binary_name}{self.extension}"

    def qualified_binary_name(self, binary_name: str) -> str:
        return f"{binary_name}-{self.value}{self.extension}"

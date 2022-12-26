# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import platform
from enum import Enum


class Platform(Enum):
    Linux_aarch64 = "linux-aarch64"
    Linux_x86_64 = "linux-x86_64"
    Macos_aarch64 = "macos-aarch64"
    Macos_x86_64 = "macos-x86_64"
    Windows_x86_64 = "windows-x86_64"

    @classmethod
    def parse(cls, value: str) -> Platform:
        return Platform.current() if "current" == value else Platform(value)

    @classmethod
    def current(cls) -> Platform:
        match (platform.system().lower(), platform.machine().lower()):
            case ("linux", "aarch64" | "arm64"):
                return cls.Linux_aarch64
            case ("linux", "amd64" | "x86_64"):
                return cls.Linux_x86_64
            case ("darwin", "aarch64" | "arm64"):
                return cls.Macos_aarch64
            case ("darwin", "amd64" | "x86_64"):
                return cls.Macos_x86_64
            case ("windows", "amd64" | "x86_64"):
                return cls.Windows_x86_64
            case _:
                raise ValueError(
                    "The current platform is not supported!: "
                    f"{platform.system()} {platform.machine()}"
                )

    @property
    def extension(self):
        return ".exe" if self is self.Windows_x86_64 else ""

    def binary_name(self, binary_name: str) -> str:
        return f"{binary_name}{self.extension}"

    def qualified_binary_name(self, binary_name: str) -> str:
        return f"{binary_name}-{self.value}{self.extension}"

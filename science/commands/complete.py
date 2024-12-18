# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from enum import Enum
from functools import cache
from typing import Self

import psutil

from science.os import EXE_EXT


class Shell(Enum):
    @classmethod
    @cache
    def current(cls) -> Self | None:
        known_shells = tuple(shell.value for shell in cls)
        process: psutil.Process | None = psutil.Process()
        if process:
            while process and (process := process.parent()):
                if (exe := process.name().rstrip(EXE_EXT).lower()) in known_shells:
                    return cls(exe)
        return None

    Bash = "bash"
    Fish = "fish"
    Zsh = "zsh"

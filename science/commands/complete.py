# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).
from enum import Enum
from functools import cache
from typing import Self

import psutil

from science.os import EXE_EXT, IS_WINDOWS


class Shell(Enum):
    @classmethod
    @cache
    def current(cls) -> Self | None:
        python_process = psutil.Process()
        if IS_WINDOWS:
            python_process = python_process.parent()
        if not python_process:
            return None

        scie_process = python_process.parent()
        if not scie_process:
            return None

        shell_process = scie_process.parent()
        if not shell_process:
            return None

        parent_exe_name = scie_process.name()
        try:
            return cls(parent_exe_name.rstrip(EXE_EXT).lower() if IS_WINDOWS else parent_exe_name)
        except ValueError:
            return None

    Bash = "bash"
    Fish = "fish"
    Zsh = "zsh"

# Copyright 2025 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

"""Just enough stubbing to get a version of psutil that limps along for musl systems.

Our PBS interpreter does not support dynamic linking and psutil builds with shared objects. As such,
we stub out just enough functionality for the complete and doc commands to function on musl systems.
"""

from __future__ import annotations

import dataclasses
import errno
import os
import signal
from dataclasses import dataclass
from typing import Iterable

from science.platform import CURRENT_PLATFORM_SPEC

try:
    import psutil

    Error = psutil.Error
    Process = psutil.Process
    NoSuchProcess = psutil.NoSuchProcess
except ImportError:

    class Error(Exception):  # type: ignore[no-redef]
        pass

    class NoSuchProcess(Error):  # type: ignore[no-redef]
        pass

    @dataclass(frozen=True)
    class Process:  # type: ignore[no-redef]
        @staticmethod
        def unavailable_error() -> Error:
            return Error(f"The psutil module is not available on {CURRENT_PLATFORM_SPEC}.")

        pid: int = dataclasses.field(default_factory=os.getpid)

        def create_time(self) -> float | None:
            return None

        def cmdline(self) -> Iterable[str]:
            raise self.unavailable_error()

        def parent(self) -> Process | None:
            return None

        def name(self) -> str:
            return ""

        def is_running(self) -> bool:
            try:
                os.kill(self.pid, 0)
                return True
            except OSError:
                return False

        def terminate(self) -> None:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except OSError as e:
                if e.errno == errno.ESRCH:
                    raise NoSuchProcess(str(e))
                raise Error(str(e))

        def kill(self) -> None:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except OSError as e:
                if e.errno == errno.ESRCH:
                    raise NoSuchProcess(str(e))
                raise Error(str(e))

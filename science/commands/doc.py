# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path, PurePath
from typing import Any

import psutil

from science import __version__
from science.cache import science_cache
from science.platform import CURRENT_PLATFORM

logger = logging.getLogger(__name__)

# SCIE -> SKI (rotate right) -> ISK (substitute 1) -> 1SK (ascii decimal) -> 1 83 75
SERVER_DEFAULT_PORT = 18375

SERVER_NAME = f"Science v{__version__} docs HTTP server"


def _server_dir(ensure: bool = False) -> Path:
    server_dir = science_cache() / "docs" / "server" / __version__
    if ensure:
        server_dir.mkdir(parents=True, exist_ok=True)
    return server_dir


def _render_unix_time(unix_time: float) -> str:
    return datetime.fromtimestamp(unix_time).strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class ServerInfo:
    url: str
    pid: int
    create_time: float

    def __str__(self) -> str:
        return f"{self.url} @ {self.pid} (started at {_render_unix_time(self.create_time)})"


@dataclass(frozen=True)
class Pidfile:
    @classmethod
    def _pidfile(cls, ensure: bool = False) -> Path:
        return _server_dir(ensure) / "pidfile"

    @classmethod
    def load(cls) -> Pidfile | None:
        pidfile = cls._pidfile()
        try:
            with pidfile.open() as fp:
                data = json.load(fp)
            return cls(
                ServerInfo(url=data["url"], pid=data["pid"], create_time=data["create_time"])
            )
        except (OSError, ValueError, KeyError) as e:
            logger.debug(f"Failed to load {SERVER_NAME} pid file from {pidfile}: {e}")
            return None

    @staticmethod
    def _read_url(server_log: Path, timeout: float) -> str | None:
        # N.B.: The simple http server module output is:
        # Serving HTTP on 0.0.0.0 port 33539 (http://0.0.0.0:33539/) ...
        # Or:
        # Serving HTTP on :: port 33539 (http://[::]:33539/) ...
        # Etc.

        start = time.time()
        while time.time() - start < timeout:
            with server_log.open() as fp:
                for line in fp:
                    match = re.search(r"Serving HTTP on \S+ port (?P<port>\d+) ", line)
                    if match:
                        port = match.group("port")
                        return "http://localhost:{port}".format(port=port)
        return None

    @classmethod
    def record(cls, server_log: Path, pid: int, timeout: float = 5.0) -> Pidfile | None:
        url = cls._read_url(server_log, timeout)
        if not url:
            return None

        try:
            create_time = psutil.Process(pid).create_time()
        except psutil.Error:
            return None

        with cls._pidfile(ensure=True).open("w") as fp:
            json.dump(dict(url=url, pid=pid, create_time=create_time), fp, indent=2, sort_keys=True)
        return cls(ServerInfo(url=url, pid=pid, create_time=create_time))

    server_info: ServerInfo

    @property
    @cache
    def _process(self) -> psutil.Process | None:
        try:
            process = psutil.Process(self.server_info.pid)
        except psutil.Error:
            return None
        else:
            try:
                create_time = process.create_time()
            except psutil.Error:
                return None
            else:
                if create_time != self.server_info.create_time:
                    try:
                        command = shlex.join(process.cmdline())
                    except psutil.Error:
                        command = "<unknown command line>"
                    logger.debug(
                        f"Pid has rolled over for {self.server_info} to {command} (started at "
                        f"{_render_unix_time(create_time)})"
                    )
                    return None
                return process

    def alive(self) -> bool:
        if process := self._process:
            try:
                return process.is_running()
            except psutil.Error:
                pass
        return False

    def kill(self) -> None:
        if process := self._process:
            process.terminate()


@dataclass(frozen=True)
class LaunchResult:
    server_info: ServerInfo
    already_running: bool


@dataclass(frozen=True)
class LaunchError(Exception):
    """Indicates an error launching the doc server."""

    log: PurePath
    additional_msg: str | None = None

    def __str__(self) -> str:
        lines = ["Error launching docs server."]
        if self.additional_msg:
            lines.append(self.additional_msg)
        lines.append("See the log at {log} for more details.".format(log=self.log))
        return os.linesep.join(lines)


def launch(
    document_root: PurePath, port: int = SERVER_DEFAULT_PORT, timeout: float = 5.0
) -> LaunchResult:
    pidfile = Pidfile.load()
    if pidfile and pidfile.alive():
        return LaunchResult(server_info=pidfile.server_info, already_running=True)

    log = _server_dir(ensure=True) / "log.txt"

    # N.B.: We set up line buffering for the process pipes as well as the underlying Python running
    # the http server to ensure we can observe the `Serving HTTP on ...` line we need to grab the
    # ephemeral port chosen.
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    with log.open("w") as fp:
        # Not proper daemonization, but good enough.
        daemon_kwargs: dict[str, Any] = (
            {
                # The subprocess.{DETACHED_PROCESS,CREATE_NEW_PROCESS_GROUP} attributes are only
                # defined on Windows.
                "creationflags": (
                    subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
                    | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
                )
            }
            if CURRENT_PLATFORM.is_windows
            else {
                # The os.setsid function is not available on Windows.
                "preexec_fn": os.setsid  # type: ignore[attr-defined]
            }
        )
        process = subprocess.Popen(
            args=[sys.executable, "-m", "http.server", str(port)],
            env=env,
            cwd=document_root,
            bufsize=1,
            stdout=fp.fileno(),
            stderr=subprocess.STDOUT,
            close_fds=True,
            **daemon_kwargs,
        )

    pidfile = Pidfile.record(server_log=log, pid=process.pid, timeout=timeout)
    if not pidfile:
        try:
            psutil.Process(process.pid).kill()
        except psutil.Error as e:
            if not isinstance(e, psutil.NoSuchProcess):
                raise LaunchError(
                    log,
                    additional_msg=(
                        f"Also failed to kill the partially launched server at pid {process.pid}: "
                        f"{e}"
                    ),
                )
        raise LaunchError(log)
    return LaunchResult(server_info=pidfile.server_info, already_running=False)


def shutdown() -> ServerInfo | None:
    pidfile = Pidfile.load()
    if not pidfile or not pidfile.alive():
        return None

    logger.debug(f"Killing {SERVER_NAME} {pidfile.server_info}")
    pidfile.kill()
    return pidfile.server_info

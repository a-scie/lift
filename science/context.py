# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import click
from appdirs import user_cache_dir


class ContextConfig:
    pass


_T = TypeVar("_T", bound=ContextConfig)


def active_context_config(config_type: type[_T]) -> _T | None:
    current_context = click.get_current_context(silent=True)
    return current_context.find_object(config_type) if current_context else None


@dataclass(frozen=True)
class ScienceConfig(ContextConfig):
    DEFAULT_CACHE_DIR = Path(user_cache_dir("science"))

    @classmethod
    def active(cls) -> ScienceConfig:
        return active_context_config(cls) or ScienceConfig()

    verbosity: int = 0
    cache_dir: Path = DEFAULT_CACHE_DIR

    @property
    def quiet(self) -> bool:
        return self.verbosity < 0

    @property
    def verbose(self) -> bool:
        return self.verbosity > 0

    def configure_logging(self, root_logger: logging.Logger):
        match self.verbosity:
            case v if v <= -2:
                root_logger.setLevel(logging.FATAL)
            case -1:
                root_logger.setLevel(logging.ERROR)
            case 0:
                root_logger.setLevel(logging.WARNING)
            case 1:
                root_logger.setLevel(logging.INFO)
            case v if v >= 2:
                root_logger.setLevel(logging.DEBUG)

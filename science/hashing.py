# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_ALGORITHM = "sha256"


class Fingerprint(str):
    pass


@dataclass(frozen=True)
class ExpectedDigest:
    fingerprint: Fingerprint
    algorithm: str = DEFAULT_ALGORITHM
    size: int | None = None

    def is_too_big(self, size: int | None) -> bool:
        return self.size is not None and size is not None and size > self.size

    def maybe_check_size(self, subject: str, actual_size: Callable[[], int]) -> None:
        if self.size is not None and (actual_bytes := actual_size()) != self.size:
            raise ValueError(
                f"The {subject} has unexpected size.\n"
                f"Expected {self.size} bytes but found {actual_bytes} bytes."
            )

    def check_fingerprint(self, subject: str, actual_fingerprint: Fingerprint) -> None:
        if self.fingerprint != actual_fingerprint:
            raise ValueError(
                f"The {subject} had unexpected contents.\n"
                f"Expected {self.algorithm} digest:\n"
                f"  {self.fingerprint}\n"
                f"Actual {self.algorithm} digest:\n"
                f"  {actual_fingerprint}"
            )

    def check(self, subject: str, actual_fingerprint: Fingerprint, actual_size: int) -> None:
        self.maybe_check_size(subject=subject, actual_size=lambda: actual_size)
        self.check_fingerprint(subject=subject, actual_fingerprint=actual_fingerprint)

    def check_path(self, path: Path, subject: str = "file") -> None:
        subject = f"{subject} at {path}"
        self.maybe_check_size(subject=subject, actual_size=lambda: path.stat().st_size)

        digest = hashlib.new(self.algorithm)
        with path.open(mode="rb") as fp:
            for chunk in iter(lambda: fp.read(io.DEFAULT_BUFFER_SIZE), b""):
                digest.update(chunk)
        self.check_fingerprint(subject=subject, actual_fingerprint=Fingerprint(digest.hexdigest()))

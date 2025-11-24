# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).


import hashlib
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, cast

from science.dataclass.reflect import documented_dataclass
from science.errors import InputError

DEFAULT_ALGORITHM = "sha256"


class Fingerprint(str):
    pass


class BinaryHasher(BinaryIO, ABC):
    @abstractmethod
    def digest(self) -> Digest:
        """Return the digest of the bytes read so far."""


class _BinaryIOHasher:
    def __init__(self, underlying: BinaryIO, algorithm: str = DEFAULT_ALGORITHM) -> None:
        self._underlying = underlying
        self._digest = hashlib.new(algorithm)
        self._read = 0

    @property
    def name(self) -> str:
        return self._underlying.name

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        data = self._underlying.read(*args, **kwargs)
        self._read += len(data)
        self._digest.update(data)
        return data

    def digest(self) -> Digest:
        return Digest(size=self._read, fingerprint=Fingerprint(self._digest.hexdigest()))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._underlying, name)


@documented_dataclass(frozen=True, alias="digest")
class Digest:
    size: int | None = None
    fingerprint: Fingerprint | None = None

    @classmethod
    def hasher(cls, underlying: BinaryIO, algorithm: str = DEFAULT_ALGORITHM) -> BinaryHasher:
        # N.B.: This cast just serves to localize squelching of MyPy warnings to a single spot.
        # MyPy cannot grok the `__getattr__` magic in use by _BinaryIOHasher for implementation of
        # the full BinaryIO interface via delegation.
        return cast(BinaryHasher, _BinaryIOHasher(underlying, algorithm=algorithm))

    @classmethod
    def hash(cls, path: Path, algorithm: str = DEFAULT_ALGORITHM) -> Digest:
        with path.open(mode="rb") as fp:
            binary_hasher = cls.hasher(fp, algorithm=algorithm)
            binary_hasher.read()
            return binary_hasher.digest()


@dataclass(frozen=True)
class ExpectedDigest:
    fingerprint: Fingerprint | None = None
    algorithm: str = DEFAULT_ALGORITHM
    size: int | None = None

    def is_too_big(self, size: int | None) -> bool:
        return self.size is not None and size is not None and size > self.size

    def maybe_check_size(self, subject: str, actual_size: Callable[[], int]) -> None:
        if self.size is not None and (actual_bytes := actual_size()) != self.size:
            raise InputError(
                f"The {subject} has unexpected size.\n"
                f"Expected {self.size} bytes but found {actual_bytes} bytes."
            )

    def check_fingerprint(self, subject: str, actual_fingerprint: Fingerprint) -> None:
        if self.fingerprint and self.fingerprint != actual_fingerprint:
            raise InputError(
                f"The {subject} has unexpected contents.\n"
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


@dataclass(frozen=True)
class Provenance:
    source: str
    digest: Digest | None = None

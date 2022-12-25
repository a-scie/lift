# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Literal, Protocol, TypeAlias

from frozendict import frozendict

from science.platform import Platform


@dataclass(frozen=True)
class Digest:
    size: int
    fingerprint: str


class FileType(Enum):
    Blob = "blob"
    Directory = "directory"
    Zip = "zip"
    Tar = "tar"
    TarGzip = "tar.gz"
    TarBzip2 = "tar.bz2"
    TarLzma = "tar.xz"
    TarZlib = "tar.Z"
    TarZstd = "tar.zst"


@dataclass(frozen=True)
class Binding:
    name: str


Source: TypeAlias = Binding | Literal["fetch"] | None


@dataclass(frozen=True)
class File:
    name: str
    key: str | None = None
    digest: Digest | None = None
    type: FileType | None = None
    is_executable: bool = False
    eager_extract: bool = False
    source: Source = None


@dataclass(frozen=True)
class Env:
    default: frozendict[str, str] = frozendict()
    replace: frozendict[str, str] = frozendict()
    remove_exact: frozenset[str] = frozenset()
    remove_re: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Command:
    exe: str
    args: tuple[str, ...] = ()
    env: Env = Env()
    name: str | None = None
    description: str | None = None


class Distribution:
    file: File
    placeholders: frozendict[str, str]


class Provider(Protocol):
    @classmethod
    def create(cls, **kwargs) -> Provider:
        ...

    def distribution(self, platform: Platform) -> Distribution | None:
        ...


@dataclass(frozen=True)
class Interpreter:
    name: str
    provider: Provider
    lazy: bool = False


@dataclass(frozen=True)
class Application:
    name: str
    commands: frozenset[Command]
    description: str | None
    load_dotenv: bool = False
    platforms: frozenset[Platform] = frozenset([Platform.current()])
    interpreters: Iterable[Interpreter] = ()
    files: Iterable[File] = ()
    bindings: frozenset[Command] = frozenset()

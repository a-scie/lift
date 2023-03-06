# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import os.path
import re
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Literal, Match, Protocol, TypeAlias, runtime_checkable

from packaging.version import Version

from science.frozendict import FrozenDict
from science.platform import Platform


class Fingerprint(str):
    pass


@dataclass(frozen=True)
class Digest:
    size: int
    fingerprint: Fingerprint


class FileType(Enum):
    @classmethod
    def for_extension(cls, extension: str) -> FileType:
        for member in cls:
            if extension == member.value:
                return member
        raise ValueError(f"No file type matches extension {extension}")

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


FileSource: TypeAlias = Binding | Literal["fetch"] | None


@dataclass(frozen=True)
class File:
    name: str
    key: str | None = None
    digest: Digest | None = None
    type: FileType | None = None
    is_executable: bool = False
    eager_extract: bool = False
    source: FileSource = None

    @property
    def id(self) -> str:
        return self.key or self.name

    @property
    def placeholder(self) -> str:
        return f"{{{self.id}}}"


@dataclass(frozen=True)
class ScieJump:
    version: Version | None = None
    digest: Digest | None = None


@dataclass(frozen=True)
class Identifier:
    @classmethod
    def parse(cls, value) -> Identifier:
        if any(char in value for char in ("{", "}", ":")):
            raise ValueError(
                f"An identifier can not contain any of '{', '}' or ':', given: {value}"
            )
        return cls(value)

    value: str


@dataclass(frozen=True)
class Ptex:
    id: Identifier = Identifier.parse("ptex")
    argv1: str = "{scie.lift}"
    version: Version | None = None
    digest: Digest | None = None

    @property
    def placeholder(self) -> str:
        return f"{{{self.id}}}"


@dataclass(frozen=True)
class Env:
    default: FrozenDict[str, str] = FrozenDict()
    replace: FrozenDict[str, str] = FrozenDict()
    remove_exact: frozenset[str] = frozenset()
    remove_re: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Command:
    exe: str
    args: tuple[str, ...] = ()
    env: Env = Env()
    name: str | None = None
    description: str | None = None


class Url(str):
    pass


DistributionSource: TypeAlias = Url | Path


@dataclass(frozen=True)
class Distribution:
    id: Identifier
    file: File
    source: DistributionSource
    placeholders: FrozenDict[Identifier, str]

    def _expand_placeholder(self, match: Match) -> str:
        if placeholder := match.group("placeholder"):
            return os.path.join(
                self.file.placeholder, self.placeholders[Identifier.parse(placeholder)]
            )
        return self.file.placeholder

    def expand_placeholders(self, value: str) -> str:
        return re.sub(
            rf"#{{{re.escape(self.id.value)}(?::(?P<placeholder>[^{{}}:]+))?}}",
            self._expand_placeholder,
            value,
        )


@runtime_checkable
class Provider(Protocol):
    @classmethod
    def create(cls, identifier: Identifier, lazy: bool, **kwargs) -> Provider:
        ...

    def distribution(self, platform: Platform) -> Distribution | None:
        ...


@dataclass(frozen=True)
class Interpreter:
    id: Identifier
    provider: Provider
    lazy: bool = False


@dataclass(frozen=True)
class InterpreterGroup:
    @classmethod
    def create(cls, id_: Identifier, selector: str, interpreters: Iterable[Interpreter]):
        interpreters_by_provider = defaultdict[Provider, list[Interpreter]](list)
        for interpreter in interpreters:
            interpreters_by_provider[interpreter.provider].append(interpreter)
        if not interpreters_by_provider:
            raise ValueError(
                "At least two interpreters must be specified to form a group and none were."
            )
        if len(interpreters_by_provider) > 1:
            given = [f"{provider}" for provider, member in interpreters_by_provider.items()]
            raise ValueError(
                f"All specified interpreters must have the same provider. Given:\n{given}"
            )
        return cls(id=id_, selector=selector, members=frozenset(interpreters))

    id: Identifier
    selector: str
    members: frozenset[Interpreter]


@dataclass(frozen=True)
class Application:
    name: str
    commands: frozenset[Command]
    description: str | None
    load_dotenv: bool = False
    scie_jump: ScieJump = ScieJump()
    ptex: Ptex | None = None
    platforms: frozenset[Platform] = frozenset([Platform.current()])
    interpreters: Iterable[Interpreter] = ()
    interpreter_groups: Iterable[InterpreterGroup] = ()
    files: Iterable[File] = ()
    bindings: frozenset[Command] = frozenset()

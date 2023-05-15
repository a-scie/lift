# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import os.path
import re
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Iterable, Match, Protocol, TypeAlias, runtime_checkable

from packaging.version import Version

from science.errors import InputError
from science.frozendict import FrozenDict
from science.hashing import ExpectedDigest, Fingerprint
from science.platform import Platform


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
        raise InputError(f"No file type matches extension {extension}")

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

    @property
    def lazy(self) -> bool:
        return True

    source_type: ClassVar[str] = "binding"


@dataclass(frozen=True)
class Fetch:
    url: Url
    lazy: bool = True

    source_type: ClassVar[str] = "url"
    binding_name: ClassVar[str] = "fetch"

    @classmethod
    def create_binding(cls, fetch_exe: File, argv1: str) -> Command:
        return Command(name=cls.binding_name, exe=fetch_exe.placeholder, args=tuple([argv1]))


FileSource: TypeAlias = Binding | Fetch | None


@dataclass(frozen=True)
class File:
    name: str
    key: str | None = None
    digest: Digest | None = None
    type: FileType | None = None
    is_executable: bool = False
    eager_extract: bool = False
    source: FileSource = None

    def __post_init__(self) -> None:
        if self.source and not self.digest:
            raise InputError(
                f"Since {self} has a {self.source.source_type} source it must also specify `size` "
                f"and `fingerprint`."
            )

    @property
    def id(self) -> str:
        return self.key or self.name

    @property
    def placeholder(self) -> str:
        return f"{{{self.id}}}"

    def maybe_check_digest(self, path: Path):
        if not self.digest:
            return
        if self.source and self.source.lazy:
            return
        expected_digest = ExpectedDigest(fingerprint=self.digest.fingerprint, size=self.digest.size)
        return expected_digest.check_path(path)


@dataclass(frozen=True)
class ScieJump:
    version: Version | None = None
    digest: Digest | None = None


@dataclass(frozen=True)
class Identifier:
    @classmethod
    def parse(cls, value) -> Identifier:
        if any(char in value for char in ("{", "}", ":")):
            raise InputError(
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
    @cached_property
    def info(self):
        return urllib.parse.urlparse(self)


@dataclass(frozen=True)
class Distribution:
    id: Identifier
    file: File
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


@dataclass(frozen=True)
class InterpreterGroup:
    @classmethod
    def create(cls, id_: Identifier, selector: str, interpreters: Iterable[Interpreter]):
        interpreters_by_provider = defaultdict[type[Provider], list[Interpreter]](list)
        for interpreter in interpreters:
            interpreters_by_provider[type(interpreter.provider)].append(interpreter)
        if not interpreters_by_provider:
            raise InputError(
                "At least two interpreters must be specified to form a group and none were."
            )
        if len(interpreters_by_provider) > 1:
            given = [f"{provider}" for provider, member in interpreters_by_provider.items()]
            raise InputError(
                f"All specified interpreters must have the same provider. Given:\n{given}"
            )
        members = frozenset(interpreters)
        if len(members) < 2:
            member = next(iter(members))
            raise InputError(
                f"At least two interpreters must be specified to form a group but only given "
                f"{member.id!r}."
            )
        return cls(id=id_, selector=selector, members=members)

    id: Identifier
    selector: str
    members: frozenset[Interpreter]

    def _expand_placeholder(self, platform: Platform, match: Match) -> tuple[str, dict[str, str]]:
        if placeholder := match.group("placeholder"):
            env = {}
            ph = Identifier.parse(placeholder)
            env_var_prefix = f"_SCIENCE_IG_{self.id.value}_{placeholder}_"
            for member in self.members:
                distribution = member.provider.distribution(platform)
                if distribution:
                    ph_value = distribution.placeholders[ph]
                    env[f"={env_var_prefix}{distribution.id.value}"] = ph_value
            path = os.path.join(
                f"{{scie.files.{self.selector}}}", f"{{scie.env.{env_var_prefix}{self.selector}}}"
            )
            return path, env
        return self.selector, {}

    def expand_placeholders(self, platform: Platform, value: str) -> tuple[str, dict[str, str]]:
        env = {}

        def expand_placeholder(match: Match) -> str:
            expansion, ig_env = self._expand_placeholder(platform, match)
            env.update(ig_env)
            return expansion

        value = re.sub(
            rf"#{{{re.escape(self.id.value)}(?::(?P<placeholder>[^{{}}:]+))?}}",
            expand_placeholder,
            value,
        )
        return value, env


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

# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import os.path
import re
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import (
    ClassVar,
    Collection,
    Iterable,
    Iterator,
    Match,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

from packaging.version import Version

from science.build_info import BuildInfo
from science.errors import InputError
from science.frozendict import FrozenDict
from science.hashing import Digest, ExpectedDigest
from science.platform import Platform
from science.types import Dataclass


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


class Identifier(str):
    def __new__(cls, value: str) -> Identifier:
        if any(char in value for char in ("{", "}", ":")):
            raise InputError(
                f"An identifier can not contain any of '{', '}' or ':', given: {value}"
            )
        return super().__new__(cls, value)


@dataclass(frozen=True)
class Ptex:
    id: Identifier = Identifier("ptex")
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
            return os.path.join(self.file.placeholder, self.placeholders[Identifier(placeholder)])
        return self.file.placeholder

    def expand_placeholders(self, value: str) -> str:
        return re.sub(
            rf"#{{{re.escape(self.id)}(?::(?P<placeholder>[^{{}}:]+))?}}",
            self._expand_placeholder,
            value,
        )


ConfigDataclass = TypeVar("ConfigDataclass", bound=Dataclass)


@runtime_checkable
class Provider(Protocol[ConfigDataclass]):
    @classmethod
    def config_dataclass(cls) -> type[ConfigDataclass]:
        ...

    @classmethod
    def create(cls, identifier: Identifier, lazy: bool, config: ConfigDataclass) -> Provider:
        ...

    def distribution(self, platform: Platform) -> Distribution | None:
        ...


@dataclass(frozen=True)
class Interpreter(Dataclass):
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
            ph = Identifier(placeholder)
            env_var_prefix = f"_SCIENCE_IG_{self.id}_{placeholder}_"
            for member in self.members:
                distribution = member.provider.distribution(platform)
                if distribution:
                    ph_value = distribution.placeholders[ph]
                    env[f"={env_var_prefix}{distribution.id}"] = ph_value
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
            rf"#{{{re.escape(self.id)}(?::(?P<placeholder>[^{{}}:]+))?}}",
            expand_placeholder,
            value,
        )
        return value, env


@dataclass(frozen=True)
class Application(Dataclass):
    name: str
    commands: frozenset[Command]
    description: str | None = None
    load_dotenv: bool = False
    scie_jump: ScieJump = ScieJump()
    ptex: Ptex | None = None
    platforms: frozenset[Platform] = frozenset([Platform.current()])
    interpreters: tuple[Interpreter, ...] = ()
    interpreter_groups: tuple[InterpreterGroup, ...] = ()
    files: tuple[File, ...] = ()
    bindings: frozenset[Command] = frozenset()
    build_info: BuildInfo | None = None

    @staticmethod
    def _ensure_unique_names(
        subject: str, commands: Iterable[Command], reserved: Collection[str] = ()
    ) -> None:
        reserved_conflicts = list[str]()

        def iter_command_names() -> Iterator[str]:
            for command in commands:
                name = command.name or ""
                if name in reserved:
                    reserved_conflicts.append(name)
                yield name

        non_unique = {
            name: count for name, count in Counter(iter_command_names()).items() if count > 1
        }
        if non_unique:
            max_width = max(len(name) for name in non_unique)
            repeats = "\n".join(
                f"{name.rjust(max_width)}: {count} instances" for name, count in non_unique.items()
            )
            raise InputError(
                f"{subject} must have unique names. Found the following repeats:\n{repeats}"
            )
        if reserved_conflicts:
            raise InputError(
                f"{subject} cannot use the reserved binding names: {', '.join(reserved_conflicts)}"
            )

    def __post_init__(self) -> None:
        if not self.platforms:
            raise InputError(
                "There must be at least one platform defined for a science application. Leave "
                "un-configured to request just the current platform."
            )

        if not self.commands:
            raise InputError("There must be at least one command defined in a science application.")
        self._ensure_unique_names(subject="Commands", commands=self.commands)

        self._ensure_unique_names(
            subject="Binding commands",
            commands=self.bindings,
            reserved=frozenset(
                file.source.binding_name
                for file in self.files
                if isinstance(file.source, Fetch) and file.source.lazy
            ),
        )

        if (
            self.interpreter_groups
            and self.scie_jump.version
            and self.scie_jump.version < Version("0.11.0")
        ):
            raise InputError(
                os.linesep.join(
                    (
                        f"Cannot use scie-jump {self.scie_jump.version}.",
                        "This configuration uses interpreter groups and these require scie-jump "
                        "v0.11.0 or greater.",
                    )
                )
            )

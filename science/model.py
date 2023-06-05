# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
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
from science.dataclass import Dataclass
from science.dataclass.reflect import Ref, documented_dataclass, metadata
from science.errors import InputError
from science.frozendict import FrozenDict
from science.hashing import Digest, ExpectedDigest
from science.platform import Platform


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


class Binding(str):
    @property
    def lazy(self) -> bool:
        return True

    source_type: ClassVar[str] = "binding"


@documented_dataclass(frozen=True, alias="source")
class Fetch:
    """Source a file by fetching it from the internet at scie run-time or scie build-time.

    ```{important}
    If the file that is being sourced has a `digest` defined, the fetched content will be checked
    against the specified digest and a mismatch will lead to an error. Without a digest defined the
    content of the fetched file will be used as-is!
    ```
    """

    url: Url = dataclasses.field(metadata=metadata("The URL of the file content to fetch."))
    lazy: bool = dataclasses.field(
        default=True,
        metadata=metadata(
            """Whether to have the built scie fetch the `url` lazily on the target machine.

            If `false`, the file will be fetched when the scie is built and directly embedded in it.
            """
        ),
    )

    source_type: ClassVar[str] = "url"
    binding_name: ClassVar[str] = "fetch"

    @classmethod
    def create_binding(cls, fetch_exe: File, argv1: str) -> Command:
        return Command(
            name=cls.binding_name,
            exe=fetch_exe.placeholder,
            args=tuple([argv1]),
            description="Fetch files not present in the scie",
        )


FileSource: TypeAlias = Fetch | Binding | None


@documented_dataclass(frozen=True, alias="file")
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


@documented_dataclass(frozen=True, alias="scie_jump")
class ScieJump:
    version: Version | None = dataclasses.field(default=None, metadata=metadata(reference=True))
    digest: Digest | None = None


class Identifier(str):
    def __new__(cls, value: str) -> Identifier:
        if any(char in value for char in ("{", "}", ":")):
            raise InputError(
                f"An identifier can not contain any of '{', '}' or ':', given: {value}"
            )
        return super().__new__(cls, value)


@documented_dataclass(frozen=True, alias="ptex")
class Ptex:
    id: Identifier = Identifier("ptex")
    argv1: str = "{scie.lift}"
    version: Version | None = dataclasses.field(default=None, metadata=metadata(reference=True))
    digest: Digest | None = None

    @property
    def placeholder(self) -> str:
        return f"{{{self.id}}}"


@documented_dataclass(frozen=True, alias="env")
class Env:
    default: FrozenDict[str, str] = FrozenDict()
    replace: FrozenDict[str, str] = FrozenDict()
    remove_exact: frozenset[str] = frozenset()
    remove_re: frozenset[str] = frozenset()


@documented_dataclass(frozen=True, kw_only=True, alias="command")
class Command:
    name: str = ""
    description: str | None = None
    exe: str
    args: tuple[str, ...] = ()
    env: Env | None = None


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


@documented_dataclass(frozen=True, alias="interpreter")
class Interpreter(Dataclass):
    id: Identifier
    provider: Provider = dataclasses.field(
        metadata=metadata(
            """The name of a Science Provider implementation.

            The built-in provider implementations are documented [here](#built-in-providers). Each 
            provider implementation can define further configuration fields which should be
            specified in this table.
            """,
            reference=True,
        )
    )


@documented_dataclass(frozen=True, alias="interpreter_group")
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
    members: frozenset[Interpreter] = dataclasses.field(
        metadata=metadata(
            f"""The `id`s of the [interpreter](#{Ref(Interpreter)})s that are members of this group.

            There must be at lease two unique ids provided to form a group.
            """,
            reference=True,
        )
    )

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


@documented_dataclass(frozen=True, alias="lift")
class Application(Dataclass):
    name: str
    description: str | None = None
    load_dotenv: bool = False
    build_info: BuildInfo | None = dataclasses.field(default=None, metadata=metadata(inline=True))
    platforms: frozenset[Platform] = frozenset([Platform.current()])
    interpreters: tuple[Interpreter, ...] = ()
    interpreter_groups: tuple[InterpreterGroup, ...] = ()
    files: tuple[File, ...] = ()
    commands: frozenset[Command] = frozenset()
    bindings: frozenset[Command] = frozenset()
    scie_jump: ScieJump | None = None
    ptex: Ptex | None = None

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
            and self.scie_jump
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

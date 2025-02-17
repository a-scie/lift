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
from pathlib import Path, PurePath
from typing import (
    Any,
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
from urllib.parse import ParseResult

from packaging.version import Version

from science.build_info import BuildInfo
from science.dataclass import Dataclass
from science.dataclass.reflect import documented_dataclass, metadata
from science.doc import Ref
from science.errors import InputError
from science.frozendict import FrozenDict
from science.hashing import Digest, ExpectedDigest
from science.platform import CURRENT_PLATFORM_SPEC, PlatformSpec


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


@documented_dataclass(
    f"""Source a file by fetching it from the internet at scie run-time or scie build-time.

    ```{{important}}
    If the file that is being sourced has a [digest](#{Ref(Digest)}) defined, the fetched
    content will be checked against the specified digest and a mismatch will lead to an error.
    Without a digest defined the content of the fetched file will be used as-is!
    ```
    """,
    frozen=True,
    alias="source",
)
class Fetch:
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


@documented_dataclass(
    f"""A file to include in the scie.

    Files are generally embedded in the scie executable and extracted as needed at run-time using
    a concurrency-safe file system cache. Archives are unpacked unless the file type is marked
    `{FileType.Blob.value!r}`
    """,
    frozen=True,
    alias="file",
)
class File:
    name: str = dataclasses.field(
        metadata=metadata(
            f"""\
            The name of the file.

            This will usually be the actual file name or the relative path to a file, but it can
            also be an abstract name. If the file name is not a relative path there are two things
            to note:
            * If the file `type` is not explicitly set, it will be inferred from the extension
              unless the file resolves as a directory, in which case it will have type
              `{FileType.Directory.value!r}`.
            * The file will need to be mapped via the `science lift --file <name>=<path> ...` option
              at build-time.
            """
        )
    )
    key: str | None = dataclasses.field(
        default=None,
        metadata=metadata(
            lambda: f"""\
            An alternate name for the file.

            The key can be used in place of the `name` in `{{<name>}}` or `{{scie.file.<name>}}`
            placeholders in [`command`](#{Ref(Command)}) fields or when mapping the the file using
            the `science lift --file <name>=<path> ...` option at build-time.
            """
        ),
    )
    digest: Digest | None = dataclasses.field(
        default=None,
        metadata=metadata(
            """The expected digest of the file.

            The digest will be checked at scie build-time if the file has no `source` and it will be
            checked again upon extraction from the scie at runtime.
            """
        ),
    )
    type: FileType | None = dataclasses.field(
        default=None,
        metadata=metadata(
            f"""The file type expected.

            ```{{note}}
            Can be set to `{FileType.Blob.value!r}` to turn off automatic extraction of recognised
            archive types.
            ```
            """
        ),
    )
    is_executable: bool = dataclasses.field(
        default=False,
        metadata=metadata(
            """Is the file an executable.

            This is auto-detected if the file has no `source` but must be set if the file is an
            executable that is provided by a `source`. This has no effect for Windows platform
            scies.
            """
        ),
    )
    eager_extract: bool = dataclasses.field(
        default=False,
        metadata=metadata(
            lambda: f"""Extract the file from the scie upon first execution of the scie.

            Although files are automatically extracted when referenced directly or indirectly by
            placeholders in the scie [`command`](#{Ref(Command)}) selected for execution, the scie
            may have other un-referenced files used by other commands that you wish to be extracted
            eagerly anyhow.
            """
        ),
    )
    source: FileSource = dataclasses.field(
        default=None,
        metadata=metadata(
            lambda: f"""A source for the file's byte content.

            Normally files are expected to be found locally at scie build-time, but you may want
            science to fetch them for you as a convenience at build time or you may want the scie
            to fetch them lazily at run-time. Specifying a [`source`](#{Ref(Fetch)}) table can
            accomplish either.

            For more exotic cases the source can be a string that is the name of a binding
            [`command`](#{Ref(Command)}) that accepts the `name` of the file as its sole argument
            and produces the file's byte content on stdout.
            """
        ),
    )

    def __post_init__(self) -> None:
        if self.source and not self.digest:
            raise InputError(
                f"File {self.id!r} has a {self.source.source_type} source it must also specify "
                "`size` and `fingerprint`."
            )
        if self.digest and self.type is FileType.Directory:
            raise InputError(
                f"File {self.id!r} is a directory and has a digest defined but digests are not "
                "supported for directories."
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


class Url(str):
    @staticmethod
    def __new__(cls, value, *args: Any, **kwargs: Any) -> Url:
        return super().__new__(cls, value)

    def __init__(self, _url, base: str | None = None) -> None:
        self._base = base

    @cached_property
    def info(self) -> ParseResult:
        return urllib.parse.urlparse(self)

    @cached_property
    def base_url(self) -> ParseResult:
        if self._base:
            return urllib.parse.urlparse(self._base)
        return self.info._replace(path="", params="", query="", fragment="")

    @cached_property
    def rel_path(self) -> PurePath:
        path = PurePath(urllib.parse.unquote_plus(self.info.path))
        if not self.base_url.path:
            return path.relative_to("/")
        base_path = PurePath(urllib.parse.unquote_plus(self.base_url.path))
        assert path.is_relative_to(
            base_path
        ), f"The base for Url {self} is configured as {self._base} which is not a not a sub-path."
        return path.relative_to(base_path)


@documented_dataclass(frozen=True, alias="scie_jump")
class ScieJump:
    _DEFAULT_BASE_URL: ClassVar[Url] = Url("https://github.com/a-scie/jump/releases")

    version: Version | None = dataclasses.field(default=None, metadata=metadata(reference=True))
    digest: Digest | None = None
    base_url: Url = dataclasses.field(
        default=_DEFAULT_BASE_URL,
        metadata=metadata(
            f"""The base URL to download scie-jump binaries from.

            Defaults to {_DEFAULT_BASE_URL} but can be configured to the `jump` sub-directory of a
            mirror created with the `science download scie-jump` command.
            """
        ),
    )


class Identifier(str):
    def __new__(cls, value: str) -> Identifier:
        if any(char in value for char in ("{", "}", ":")):
            raise InputError(
                f"An identifier can not contain any of '{", "}' or ':', given: {value}"
            )
        return super().__new__(cls, value)


@documented_dataclass(frozen=True, alias="ptex")
class Ptex:
    _DEFAULT_BASE_URL: ClassVar[Url] = Url("https://github.com/a-scie/ptex/releases")

    id: Identifier = Identifier("ptex")
    argv1: str = "{scie.lift}"
    version: Version | None = dataclasses.field(default=None, metadata=metadata(reference=True))
    digest: Digest | None = None
    base_url: Url = dataclasses.field(
        default=_DEFAULT_BASE_URL,
        metadata=metadata(
            f"""The base URL to download ptex binaries from.

            Defaults to {_DEFAULT_BASE_URL} but can be configured to the `ptex` sub-directory of a
            mirror created with the `science download ptex` command.
            """
        ),
    )

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


class DistributionsManifest(Protocol):
    def serialize(self, base_dir: Path) -> None: ...


ConfigDataclass = TypeVar("ConfigDataclass", bound=Dataclass)


@runtime_checkable
class Provider(Protocol[ConfigDataclass]):
    @classmethod
    def iter_supported_platforms(
        cls, requested_platforms: Iterable[PlatformSpec]
    ) -> Iterator[PlatformSpec]:
        for platform_spec in requested_platforms:
            yield platform_spec

    @classmethod
    def config_dataclass(cls) -> type[ConfigDataclass]: ...

    @classmethod
    def create(cls, identifier: Identifier, lazy: bool, config: ConfigDataclass) -> Provider: ...

    def distributions(self) -> DistributionsManifest: ...

    def distribution(self, platform_spec: PlatformSpec) -> Distribution | None: ...


@documented_dataclass(
    f"""An interpreter distribution.

    For example, a CPython distribution from [Python Standalone Builds][PBS] or a JDK archive.

    These are supplied by [Providers](#built-in-providers) and produce a [`file`](#{Ref(File)})
    entry in the scie with special `#{{<id>:<name>}}` placeholder support for accessing named files
    within the distribution archive.

    [PBS]: https://gregoryszorc.com/docs/python-build-standalone/main
    """,
    frozen=True,
    alias="interpreter",
)
class Interpreter(Dataclass):
    id: Identifier = dataclasses.field(
        metadata=metadata(
            lambda: f"""An identifier to use in `#{{<id>...}}` placeholders.

            The `#{{<id>}}` placeholder can be used in [`command`](#{Ref(Command)}) fields to
            reference the interpreter distribution archive. The `#{{<id>:<name>}}` placeholder can
            be used to reference named files provided by the interpreter distribution.
            """
        )
    )
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
    lazy: bool = dataclasses.field(
        default=False,
        metadata=metadata(
            f"""Whether to lazily fetch the interpreter distribution at scie run-time.

            By default, the interpreter distribution is fetched and embedded in the scie at
            build-time.

            ```{{note}}
            Science uses [`ptex`](https://github.com/a-scie/ptex) to perform lazy run-time fetching
            and will embed it as a [`file`](#{Ref(File)}) in the scie. You can control the version
            used and other aspects of the fetch with the [`ptex` table](#{Ref(Ptex)}).
            ```
            """,
        ),
    )


@documented_dataclass(
    f"""A group of [`interpreters`][1] from the same provider that can be dynamically selected from.

    An interpreter group is useful if you want to ship a single scie binary that can dynamically
    select an appropriate interpreter at runtime.

    ```{{tip}}
    To cut down on assembled scie size, it generally makes sense to mark all or all but one
    interpreter distribution in the group as `lazy = true`.
    ```

    [1]: #{Ref(Interpreter)}
    """,
    frozen=True,
    alias="interpreter_group",
)
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

    id: Identifier = dataclasses.field(
        metadata=metadata(
            f"""An identifier to use in `#{{<id>...}}` placeholders.

            These work just like [`interpreter`](#{Ref(Interpreter)}) ids, proxying through to the
            interpreter group member selected by the `selector`.
            """
        )
    )
    selector: str = dataclasses.field(
        metadata=metadata(
            f"""A string, that should resolve to the `id` of a member of the group.

            The selector is resolved in the same manner as [`command`](#{Ref(Command)}) fields where
            any placeholders are recursively resolved.
            """
        )
    )
    members: frozenset[Interpreter] = dataclasses.field(
        metadata=metadata(
            f"""The ids of the [`interpreter`](#{Ref(Interpreter)})s that are members of this group.

            There must be at lease two unique ids provided to form a group.
            """,
            reference=True,
        )
    )

    def _expand_placeholder(
        self, platform_spec: PlatformSpec, match: Match
    ) -> tuple[str, dict[str, str]]:
        if placeholder := match.group("placeholder"):
            env = {}
            ph = Identifier(placeholder)
            env_var_prefix = f"_SCIENCE_IG_{self.id}_{placeholder}_"
            for member in self.members:
                distribution = member.provider.distribution(platform_spec)
                if distribution:
                    ph_value = distribution.placeholders[ph]
                    env[f"={env_var_prefix}{distribution.id}"] = ph_value
            path = os.path.join(
                f"{{scie.files.{self.selector}}}", f"{{scie.env.{env_var_prefix}{self.selector}}}"
            )
            return path, env
        return self.selector, {}

    def expand_placeholders(
        self, platform_spec: PlatformSpec, value: str
    ) -> tuple[str, dict[str, str]]:
        env = {}

        def expand_placeholder(match: Match) -> str:
            expansion, ig_env = self._expand_placeholder(platform_spec, match)
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
    platform_specs: frozenset[PlatformSpec] = dataclasses.field(
        default=frozenset([CURRENT_PLATFORM_SPEC]), metadata=metadata(alias="platforms")
    )
    base: str | None = dataclasses.field(
        default=None,
        metadata=metadata("An alternate path to use for the scie base `nce` CAS."),
    )
    interpreters: tuple[Interpreter, ...] = ()
    interpreter_groups: tuple[InterpreterGroup, ...] = ()
    files: tuple[File, ...] = ()
    commands: tuple[Command, ...] = ()
    bindings: tuple[Command, ...] = ()
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
                f"{subject} cannot use the reserved binding names: {", ".join(reserved_conflicts)}"
            )

    def __post_init__(self) -> None:
        if not self.platform_specs:
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

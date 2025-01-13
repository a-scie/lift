# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from json import JSONDecodeError
from netrc import NetrcParseError
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO, ClassVar, Iterator, Mapping, Protocol

import click
import httpx
from httpx import HTTPStatusError, Request, Response, SyncByteStream, TimeoutException, codes
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)
from tqdm import tqdm

from science import VERSION, hashing
from science.cache import CacheEntry, Missing, download_cache
from science.errors import InputError
from science.hashing import Digest, ExpectedDigest, Fingerprint
from science.model import Url
from science.platform import CURRENT_PLATFORM

logger = logging.getLogger(__name__)


retry_fetch = retry(
    # Raise the final exception in a retry chain if all retries fail.
    reraise=True,
    retry=retry_if_exception(
        lambda ex: (
            isinstance(ex, TimeoutException)
            or (
                # See: https://tools.ietf.org/html/rfc2616#page-39
                isinstance(ex, HTTPStatusError)
                and ex.response.status_code
                in (
                    408,  # Request Time-out
                    500,  # Internal Server Error
                    502,  # Bad Gateway
                    503,  # Service Unavailable
                    504,  # Gateway Time-out
                )
            )
        )
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, exp_base=2, jitter=0.5),
    # This logs the retries since there is a sleep before each (see wait above).
    before_sleep=before_sleep_log(logger, logging.WARNING),
)


class AmbiguousAuthError(InputError):
    """Indicates more than one form of authentication was configured for a given URL."""


class InvalidAuthError(InputError):
    """Indicates the configured authentication for a given URL is invalid."""


def _configure_auth(url: Url) -> httpx.Auth | tuple[str, str] | None:
    if not url.info.hostname:
        return None

    normalized_hostname = url.info.hostname.upper().replace(".", "_").replace("-", "_")
    env_auth_prefix = f"SCIENCE_AUTH_{normalized_hostname}"
    env_auth = {key: value for key, value in os.environ.items() if key.startswith(env_auth_prefix)}

    def check_ambiguous_auth(auth_type: str) -> None:
        if env_auth:
            raise AmbiguousAuthError(
                f"{auth_type.capitalize()} auth was configured for {url} via env var but so was: "
                f"{", ".join(env_auth)}"
            )

    def get_username(auth_type: str) -> str | None:
        return env_auth.pop(f"{env_auth_prefix}_{auth_type.upper()}_USER", None)

    def require_password(auth_type: str) -> str:
        env_var = f"{env_auth_prefix}_{auth_type.upper()}_PASS"
        passwd = env_auth.pop(env_var, None)
        if not passwd:
            raise InvalidAuthError(
                f"{auth_type.capitalize()} auth requires a password be configured via the "
                f"{env_var} env var."
            )
        return passwd

    if bearer := env_auth.pop(f"{env_auth_prefix}_BEARER", None):
        check_ambiguous_auth("bearer")
        return "Authorization", f"Bearer {bearer}"

    if username := get_username("basic"):
        password = require_password("basic")
        check_ambiguous_auth("basic")
        return httpx.BasicAuth(username=username, password=password)

    if username := get_username("digest"):
        password = require_password("digest")
        check_ambiguous_auth("digest")
        return httpx.DigestAuth(username=username, password=password)

    try:
        return httpx.NetRCAuth(None)
    except (FileNotFoundError, IsADirectoryError):
        pass
    except NetrcParseError as e:
        logger.warning(f"Not using netrc for auth, netrc file is invalid: {e}")

    return None


class Client(Protocol):
    def __enter__(self) -> Client: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None: ...

    def get(self, url: Url) -> Response: ...

    def head(self, url: Url) -> Response: ...

    @contextmanager
    def stream(self, method: str, url: Url) -> Iterator[Response]: ...


class FileClient:
    def __enter__(self) -> Client:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        return None

    @staticmethod
    def _vet_request(url: Url, method: str = "GET") -> tuple[Request, Path] | Response:
        request = Request(method=method, url=url)
        if request.method not in ("GET", "HEAD"):
            return Response(status_code=codes.METHOD_NOT_ALLOWED, request=request)

        raw_path = urllib.parse.unquote_plus(url.info.path)
        if CURRENT_PLATFORM.is_windows:
            # Handle `file:///C:/a/path` -> `C:/a/path`.
            parts = raw_path.split("/")
            if ":" == parts[1][-1]:
                parts.pop(0)
            path = Path("/".join(parts))
        else:
            path = Path(raw_path)

        if not path.exists():
            return Response(status_code=codes.NOT_FOUND, request=request)
        if not path.is_file():
            return Response(status_code=codes.BAD_REQUEST, request=request)
        if not os.access(path, os.R_OK):
            return Response(status_code=codes.FORBIDDEN, request=request)

        return request, path

    def head(self, url: Url) -> Response:
        result = self._vet_request(url)
        if isinstance(result, Response):
            return result

        request, path = result
        return httpx.Response(
            status_code=codes.OK,
            headers={"Content-Length": str(path.stat().st_size)},
            request=request,
        )

    def get(self, url: Url) -> Response:
        result = self._vet_request(url)
        if isinstance(result, Response):
            return result

        request, path = result
        content = path.read_bytes()
        return httpx.Response(
            status_code=codes.OK,
            headers={"Content-Length": str(len(content))},
            content=content,
            request=request,
        )

    @dataclass(frozen=True)
    class FileByteStream(SyncByteStream):
        stream: BinaryIO

        def __iter__(self) -> Iterator[bytes]:
            return iter(lambda: self.stream.read(io.DEFAULT_BUFFER_SIZE), b"")

        def close(self) -> None:
            self.stream.close()

    @contextmanager
    def stream(self, method: str, url: Url) -> Iterator[httpx.Response]:
        result = self._vet_request(url, method=method)
        if isinstance(result, Response):
            yield result
            return

        request, path = result
        with path.open("rb") as fp:
            yield httpx.Response(
                status_code=codes.OK,
                headers={"Content-Length": str(path.stat().st_size)},
                stream=self.FileByteStream(fp),
                request=request,
            )


def configured_client(url: Url, headers: Mapping[str, str] | None = None) -> Client:
    if "file" == url.info.scheme:
        return FileClient()
    headers = dict(headers) if headers else {}
    headers.setdefault("User-Agent", f"science/{VERSION}")
    auth = _configure_auth(url) if "Authorization" not in headers else None
    return httpx.Client(follow_redirects=True, headers=headers, auth=auth)


@retry_fetch
def _fetch_to_cache(
    url: Url, ttl: timedelta | None = None, headers: Mapping[str, str] | None = None
) -> Path:
    with download_cache().get_or_create(url, ttl=ttl) as cache_result:
        match cache_result:
            case Missing(_) as cache_entry:
                with (
                    configured_client(url, headers).stream("GET", url) as response,
                    cache_entry.work_path.open("wb") as cache_fp,
                ):
                    response.raise_for_status()
                    for data in response.iter_bytes():
                        cache_fp.write(data)
    return cache_result.path


def fetch_text(
    url: Url, ttl: timedelta | None = None, headers: Mapping[str, str] | None = None
) -> str:
    return _fetch_to_cache(url, ttl, headers).read_text()


def fetch_json(
    url: Url, ttl: timedelta | None = None, headers: Mapping[str, str] | None = None
) -> dict[str, Any]:
    with _fetch_to_cache(url, ttl, headers).open() as fp:
        return json.load(fp)


def _maybe_expected_digest(
    fingerprint: Digest | Fingerprint | Url | None,
    algorithm: str = hashing.DEFAULT_ALGORITHM,
    headers: Mapping[str, str] | None = None,
) -> ExpectedDigest | None:
    match fingerprint:
        case Digest(fingerprint=fingerprint, size=size):
            return ExpectedDigest(fingerprint=fingerprint, algorithm=algorithm, size=size)
        case Fingerprint(_):
            return ExpectedDigest(fingerprint=fingerprint, algorithm=algorithm)
        case Url(url):
            with configured_client(url, headers) as client:
                return ExpectedDigest(
                    fingerprint=Fingerprint(client.get(url).text.split(" ", 1)[0].strip()),
                    algorithm=algorithm,
                )

    return None


def _expected_digest(
    url: Url,
    headers: Mapping[str, str] | None = None,
    fingerprint: Digest | Fingerprint | Url | None = None,
    algorithm: str = hashing.DEFAULT_ALGORITHM,
) -> ExpectedDigest:
    expected_digest = _maybe_expected_digest(fingerprint, algorithm=algorithm, headers=headers)
    if expected_digest:
        return expected_digest

    with configured_client(url, headers) as client:
        return ExpectedDigest(
            fingerprint=Fingerprint(
                client.get(Url(f"{url}.{algorithm}")).text.split(" ", 1)[0].strip()
            ),
            algorithm=algorithm,
        )


@dataclass(frozen=True)
class FetchResult:
    class LoadError(Exception):
        """Indicates an error loading a cached fetch result."""

    _DIGEST_FILE: ClassVar[str] = "digest.json"

    @classmethod
    def load(cls, cache_entry: CacheEntry) -> FetchResult:
        try:
            digest = json.loads((cache_entry.aux_dir / cls._DIGEST_FILE).read_text())
        except (OSError, JSONDecodeError) as e:
            raise cls.LoadError() from e
        try:
            digest = Digest(size=digest["size"], fingerprint=Fingerprint(digest["hash"]))
        except (KeyError, TypeError, ValueError) as e:
            raise cls.LoadError() from e
        return cls(path=cache_entry.path, digest=digest)

    path: Path
    digest: Digest

    def dump(self, cache_entry: Missing) -> None:
        (cache_entry.work_aux_dir / self._DIGEST_FILE).write_text(
            json.dumps({"size": self.digest.size, "hash": self.digest.fingerprint})
        )


@retry_fetch
def fetch_and_verify(
    url: Url,
    fingerprint: Digest | Fingerprint | Url | None = None,
    digest_algorithm: str = hashing.DEFAULT_ALGORITHM,
    executable: bool = False,
    ttl: timedelta | None = None,
    headers: Mapping[str, str] | None = None,
) -> FetchResult:
    with download_cache().get_or_create(url, ttl=ttl) as cache_entry:
        if isinstance(cache_entry, Missing):
            click.secho(f"Downloading {url} ...", fg="green")
            with configured_client(url, headers) as client:
                expected_digest = _expected_digest(
                    url, headers, fingerprint, algorithm=digest_algorithm
                )
                digest = hashlib.new(digest_algorithm)
                total_bytes = 0
                with (
                    client.stream("GET", url) as response,
                    cache_entry.work_path.open("wb") as cache_fp,
                ):
                    response.raise_for_status()
                    total = (
                        int(content_length)
                        if (content_length := response.headers.get("Content-Length"))
                        else None
                    )
                    if expected_digest.is_too_big(total):
                        raise InputError(
                            f"The content at {url} is expected to be {expected_digest.size} "
                            f"bytes, but advertises a Content-Length of {total} bytes."
                        )
                    with tqdm(
                        total=total, unit_scale=True, unit_divisor=1024, unit="B"
                    ) as progress:
                        num_bytes_downloaded = response.num_bytes_downloaded
                        for data in response.iter_bytes():
                            total_bytes += len(data)
                            if expected_digest.is_too_big(total_bytes):
                                raise InputError(
                                    f"The download from {url} was expected to be "
                                    f"{expected_digest.size} bytes, but downloaded "
                                    f"{total_bytes} so far."
                                )
                            digest.update(data)
                            cache_fp.write(data)
                            progress.update(response.num_bytes_downloaded - num_bytes_downloaded)
                            num_bytes_downloaded = response.num_bytes_downloaded
                fingerprint = Fingerprint(digest.hexdigest())
                expected_digest.check(
                    subject=f"download from {url}",
                    actual_fingerprint=fingerprint,
                    actual_size=total_bytes,
                )
                fetch_result = FetchResult(
                    path=cache_entry.path, digest=Digest(size=total_bytes, fingerprint=fingerprint)
                )
                if executable:
                    cache_entry.work_path.chmod(0o755)
                fetch_result.dump(cache_entry)
                return fetch_result

    try:
        return FetchResult.load(cache_entry)
    except FetchResult.LoadError as e:
        logger.warning(f"Re-creating unreadable cache entry for {url}: {e}")
        cache_entry.delete()
        return fetch_and_verify(
            url=url,
            fingerprint=fingerprint,
            digest_algorithm=digest_algorithm,
            executable=executable,
            ttl=ttl,
            headers=headers,
        )

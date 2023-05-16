# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import hashlib
import json
import logging
import os
from datetime import timedelta
from netrc import NetrcParseError
from pathlib import Path
from typing import Any, Mapping

import click
import httpx
from tqdm import tqdm

from science import hashing
from science.cache import Missing, download_cache
from science.errors import InputError
from science.hashing import Digest, ExpectedDigest, Fingerprint
from science.model import Url

logger = logging.getLogger(__name__)


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
                f"{', '.join(env_auth)}"
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
    except FileNotFoundError:
        pass
    except NetrcParseError as e:
        logger.warning(f"Not using netrc for auth, netrc file is invalid: {e}")

    return None


def _configured_client(url: Url, headers: Mapping[str, str] | None = None) -> httpx.Client:
    headers = dict(headers) if headers else {}
    auth = _configure_auth(url) if "Authorization" not in headers else None
    return httpx.Client(follow_redirects=True, headers=headers, auth=auth)


def _fetch_to_cache(
    url: Url, ttl: timedelta | None = None, headers: Mapping[str, str] | None = None
) -> Path:
    with download_cache().get_or_create(url, ttl=ttl) as cache_result:
        match cache_result:
            case Missing(work=work):
                with _configured_client(url, headers).stream("GET", url) as response, work.open(
                    "wb"
                ) as cache_fp:
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
            with _configured_client(url, headers) as client:
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

    with _configured_client(url, headers) as client:
        return ExpectedDigest(
            fingerprint=Fingerprint(client.get(f"{url}.{algorithm}").text.split(" ", 1)[0].strip()),
            algorithm=algorithm,
        )


def fetch_and_verify(
    url: Url,
    fingerprint: Digest | Fingerprint | Url | None = None,
    digest_algorithm: str = hashing.DEFAULT_ALGORITHM,
    executable: bool = False,
    ttl: timedelta | None = None,
    headers: Mapping[str, str] | None = None,
) -> Path:
    verified_fingerprint = False
    with download_cache().get_or_create(url, ttl=ttl) as cache_result:
        match cache_result:
            case Missing(work=work):
                click.secho(f"Downloading {url} ...", fg="green")
                with _configured_client(url, headers) as client:
                    expected_digest = _expected_digest(
                        url, headers, fingerprint, algorithm=digest_algorithm
                    )
                    digest = hashlib.new(digest_algorithm)
                    total_bytes = 0
                    with client.stream("GET", url) as response, work.open("wb") as cache_fp:
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
                                progress.update(
                                    response.num_bytes_downloaded - num_bytes_downloaded
                                )
                                num_bytes_downloaded = response.num_bytes_downloaded
                    expected_digest.check(
                        subject=f"download from {url}",
                        actual_fingerprint=Fingerprint(digest.hexdigest()),
                        actual_size=total_bytes,
                    )
                    verified_fingerprint = True
                    if executable:
                        work.chmod(0o755)

    if not verified_fingerprint:
        expected_cached_digest = _maybe_expected_digest(
            fingerprint, headers=headers, algorithm=digest_algorithm
        )
        if expected_cached_digest:
            expected_cached_digest.check_path(
                subject=f"cached download from {url}",
                path=cache_result.path,
            )

    return cache_result.path

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

from science.cache import Missing, download_cache
from science.model import Fingerprint, Url

logger = logging.getLogger(__name__)


class AmbiguousAuthError(Exception):
    """Indicates more than one form of authentication was configured for a given URL."""


class InvalidAuthError(Exception):
    """Indicates the configured authentication for a given URL is invalid."""


def configured_client(url: Url, headers: Mapping[str, str] | None = None) -> httpx.Client:
    headers = dict(headers) if headers else {}
    auth: httpx.Auth | tuple[str, str] | None = None
    if url.info.hostname and "Authorization" not in headers:
        normalized_hostname = url.info.hostname.upper().replace(".", "_").replace("-", "_")
        env_auth_prefix = f"SCIENCE_AUTH_{normalized_hostname}_"
        env_auth = {
            key: value for key, value in os.environ.items() if key.startswith(env_auth_prefix)
        }

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
            auth = "Authorization", f"Bearer {bearer}"
        elif username := get_username("basic"):
            password = require_password("basic")
            check_ambiguous_auth("basic")
            auth = httpx.BasicAuth(username=username, password=password)
        elif username := get_username("digest"):
            password = require_password("digest")
            check_ambiguous_auth("digest")
            auth = httpx.DigestAuth(username=username, password=password)
        else:
            try:
                auth = httpx.NetRCAuth(None)
            except FileNotFoundError:
                pass
            except NetrcParseError as e:
                logger.warning(f"Not using netrc for auth, netrc file is invalid: {e}")

    return httpx.Client(follow_redirects=True, headers=headers, auth=auth)


def _fetch_to_cache(
    url: Url, ttl: timedelta | None = None, headers: Mapping[str, str] | None = None
) -> Path:
    with download_cache().get_or_create(url, ttl=ttl) as cache_result:
        match cache_result:
            case Missing(work=work):
                with configured_client(url, headers).stream("GET", url) as response, work.open(
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


def fetch_and_verify(
    url: Url,
    fingerprint: Fingerprint | Url | None = None,
    digest_algorithm: str = "sha256",
    executable: bool = False,
    ttl: timedelta | None = None,
    headers: Mapping[str, str] | None = None,
) -> Path:
    with download_cache().get_or_create(url, ttl=ttl) as cache_result:
        match cache_result:
            case Missing(work=work):
                click.secho(f"Downloading {url} ...", fg="green")
                with configured_client(url, headers) as client:
                    match fingerprint:
                        case Fingerprint(_):
                            expected_fingerprint = fingerprint
                        case Url(url):
                            expected_fingerprint = Fingerprint(
                                client.get(url).text.split(" ", 1)[0].strip()
                            )
                        case None:
                            expected_fingerprint = Fingerprint(
                                client.get(f"{url}.sha256").text.split(" ", 1)[0].strip()
                            )
                    digest = hashlib.new(digest_algorithm)
                    with client.stream("GET", url) as response, work.open("wb") as cache_fp:
                        total = (
                            int(content_length)
                            if (content_length := response.headers.get("Content-Length"))
                            else None
                        )
                        with tqdm(
                            total=total, unit_scale=True, unit_divisor=1024, unit="B"
                        ) as progress:
                            num_bytes_downloaded = response.num_bytes_downloaded
                            for data in response.iter_bytes():
                                digest.update(data)
                                cache_fp.write(data)
                                progress.update(
                                    response.num_bytes_downloaded - num_bytes_downloaded
                                )
                                num_bytes_downloaded = response.num_bytes_downloaded
                    actual_fingerprint = digest.hexdigest()
                    if expected_fingerprint != actual_fingerprint:
                        raise ValueError(
                            f"The download from {url} had unexpected contents.\n"
                            f"Expected sha256 digest:\n"
                            f"  {expected_fingerprint}\n"
                            f"Actual sha256 digest:\n"
                            f"  {actual_fingerprint}"
                        )
                    if executable:
                        work.chmod(0o755)

    return cache_result.path

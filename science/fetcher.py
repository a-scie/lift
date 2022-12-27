# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import click
import httpx
from tqdm import tqdm

from science.cache import Missing, download_cache
from science.model import Fingerprint, Url


def fetch_text(url: Url, ttl: timedelta | None = None) -> str:
    with download_cache().get_or_create(url, ttl=ttl) as cache_result:
        match cache_result:
            case Missing(work=work):
                with httpx.stream("GET", url, follow_redirects=True) as response, work.open(
                    "wb"
                ) as cache_fp:
                    for data in response.iter_bytes():
                        cache_fp.write(data)

    return cache_result.path.read_text()


def fetch_json(url: Url, ttl: timedelta | None = None) -> dict[str, Any]:
    with download_cache().get_or_create(url, ttl=ttl) as cache_result:
        match cache_result:
            case Missing(work=work):
                with httpx.stream("GET", url, follow_redirects=True) as response, work.open(
                    "wb"
                ) as cache_fp:
                    for data in response.iter_bytes():
                        cache_fp.write(data)

    with cache_result.path.open() as fp:
        return json.load(fp)


def fetch_and_verify(
    url: Url,
    fingerprint: Fingerprint | Url | None = None,
    digest_algorithm: str = "sha256",
    executable: bool = False,
    ttl: timedelta | None = None,
) -> Path:
    with download_cache().get_or_create(url, ttl=ttl) as cache_result:
        match cache_result:
            case Missing(work=work):
                click.secho(f"Downloading {url} ...", fg="green")
                with httpx.Client(follow_redirects=True) as client:
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

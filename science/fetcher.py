# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import hashlib
from pathlib import Path

import click
import httpx
from tqdm import tqdm

from science.cache import Missing, download_cache


def fetch_and_verify(url: str, dest: Path, executable: bool = False) -> None:
    with download_cache().get_or_create(url) as cache_result:
        match cache_result:
            case Missing(work=work):
                click.secho(f"Downloading {url} ...", fg="green")
                with httpx.Client(follow_redirects=True) as client:
                    expected_fingerprint = client.get(f"{url}.sha256").text.split(" ", 1)[0].strip()
                    digest = hashlib.sha256()
                    with client.stream("GET", url) as response, work.open("wb") as cache_fp:
                        total = int(response.headers["Content-Length"])
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
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(cache_result.path)

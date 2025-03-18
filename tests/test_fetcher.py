# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).
import base64
import shutil
from pathlib import Path

import httpx
from pytest import MonkeyPatch
from pytest_httpx import HTTPXMock
from testing import issue

from science.fetcher import fetch_json, fetch_text
from science.model import Url


@issue(71, ignore=True)
def test_netrc_directory(_, tmp_path: Path, monkeypatch: MonkeyPatch, cache_dir: Path) -> None:
    def assert_fetch() -> None:
        # N.B.: Ensure a fresh, un-cached fetch.
        shutil.rmtree(cache_dir, ignore_errors=True)
        assert (
            "7ed49bb4c50960d4ade3cf9a5614bd9c1190cc57d330492e36a7ace22b8ebc3b "
            "*science-fat-linux-aarch64\n"
        ) == fetch_text(
            Url(
                "https://github.com/a-scie/lift/releases/download/v0.4.2/"
                "science-fat-linux-aarch64.sha256"
            )
        )

    assert_fetch()

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    (home_dir / ".netrc").mkdir(parents=True)
    assert_fetch()


def assert_auth(
    httpx_mock: HTTPXMock, cache_dir: Path, *, expected_authorization_header_value: str
) -> None:
    # N.B.: Ensure a fresh, un-cached fetch.
    shutil.rmtree(cache_dir, ignore_errors=True)

    def reflect_headers(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=dict(request.headers.multi_items()))

    httpx_mock.add_callback(reflect_headers)

    headers = httpx.Headers(
        fetch_json(
            Url("https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest")
        )
    )
    assert expected_authorization_header_value == headers.get(
        "Authorization"
    ), f"Got headers: {headers}"


def test_basic_auth(httpx_mock: HTTPXMock, cache_dir: Path) -> None:
    with MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("SCIENCE_AUTH_API_GITHUB_COM_BASIC_USER", "Arthur")
        monkeypatch.setenv("SCIENCE_AUTH_API_GITHUB_COM_BASIC_PASS", "Dent")
        assert_auth(
            httpx_mock,
            cache_dir,
            expected_authorization_header_value=f"Basic {base64.b64encode(b'Arthur:Dent').decode()}",
        )


@issue(127, ignore=True)
def test_bearer_auth(_, httpx_mock: HTTPXMock, cache_dir: Path) -> None:
    with MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("SCIENCE_AUTH_API_GITHUB_COM_BEARER", "Zaphod")
        assert_auth(httpx_mock, cache_dir, expected_authorization_header_value="Bearer Zaphod")

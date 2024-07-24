# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import shutil
from pathlib import Path

from pytest import MonkeyPatch
from testing import issue

from science.fetcher import fetch_text
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

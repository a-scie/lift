# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).


from science.frozendict import FrozenDict
from science.hashing import Digest, Fingerprint
from science.model import Distribution, Fetch, File, Identifier, Url
from science.platform import Platform, PlatformSpec


def test_distribution_unix() -> None:
    distribution = Distribution(
        id=Identifier("cpython"),
        file=File(
            name="cpython-3.10.9+20221220-x86_64-unknown-linux-gnu-install_only.tar.gz",
            key="cpython310",
            digest=Digest(
                size=27579433,
                fingerprint=Fingerprint(
                    "5eabd117850cf92280569db874f3548d90048abc8ce55c315aeefd69d2ad6e44"
                ),
            ),
            source=Fetch(
                url=Url(
                    "https://github.com/astral-sh/python-build-standalone/releases/download/"
                    "20221220/"
                    "cpython-3.10.9%2B20221220-x86_64-unknown-linux-gnu-install_only.tar.gz"
                )
            ),
        ),
        placeholders=FrozenDict(
            {
                Identifier("python"): "python/bin/python",
                Identifier("pip"): "python/bin/pip",
            }
        ),
    )

    linux = PlatformSpec(Platform.Linux_x86_64)

    assert "foo" == distribution.expand_placeholders(linux, "foo")
    assert "#{foo}" == distribution.expand_placeholders(linux, "#{foo}")
    assert "{cpython}" == distribution.expand_placeholders(linux, "{cpython}")
    assert "{cpython310}/arbitrary/path" == distribution.expand_placeholders(
        linux, "#{cpython}/arbitrary/path"
    )
    assert "{cpython310}/python/bin/python" == distribution.expand_placeholders(
        linux, "#{cpython:python}"
    )
    assert "{cpython310}/python/bin/pip" == distribution.expand_placeholders(
        linux, "#{cpython:pip}"
    )


def test_distribution_windows() -> None:
    distribution = Distribution(
        id=Identifier("cpython"),
        file=File(
            name="cpython-3.10.18+20250702-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
            key="cpython310",
            digest=Digest(
                size=22380849,
                fingerprint=Fingerprint(
                    "1d9028a8b16a2dddfd0334a12195eb37653e4ba3dd4691059a58dc18c9c2bad5"
                ),
            ),
            source=Fetch(
                url=Url(
                    "https://github.com/astral-sh/python-build-standalone/releases/download/"
                    "20250702/"
                    "cpython-3.10.18%2B20250702-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
                )
            ),
        ),
        placeholders=FrozenDict({Identifier("python"): "python\\python.exe"}),
    )

    windows = PlatformSpec(Platform.Windows_x86_64)

    assert "foo" == distribution.expand_placeholders(windows, "foo")
    assert "#{foo}" == distribution.expand_placeholders(windows, "#{foo}")
    assert "{cpython}" == distribution.expand_placeholders(windows, "{cpython}")
    assert "{cpython310}/arbitrary/path" == distribution.expand_placeholders(
        windows, "#{cpython}/arbitrary/path"
    )
    assert r"{cpython310}\python\python.exe" == distribution.expand_placeholders(
        windows, "#{cpython:python}"
    )

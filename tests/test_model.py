# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os.path

from science.frozendict import FrozenDict
from science.hashing import Digest, Fingerprint
from science.model import Distribution, Fetch, File, Identifier, Url


def test_distribution() -> None:
    distribution = Distribution(
        id=Identifier.parse("cpython"),
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
                    "https://github.com/indygreg/python-build-standalone/releases/download/"
                    "20221220/"
                    "cpython-3.10.9%2B20221220-x86_64-unknown-linux-gnu-install_only.tar.gz"
                )
            ),
        ),
        placeholders=FrozenDict(
            {
                Identifier.parse("python"): "python/bin/python",
                Identifier.parse("pip"): "python/bin/pip",
            }
        ),
    )

    assert "foo" == distribution.expand_placeholders("foo")
    assert "#{foo}" == distribution.expand_placeholders("#{foo}")
    assert "{cpython}" == distribution.expand_placeholders("{cpython}")
    assert "{cpython310}/arbitrary/path" == distribution.expand_placeholders(
        "#{cpython}/arbitrary/path"
    )
    assert os.path.join("{cpython310}", "python/bin/python") == distribution.expand_placeholders(
        "#{cpython:python}"
    )
    assert os.path.join("{cpython310}", "python/bin/pip") == distribution.expand_placeholders(
        "#{cpython:pip}"
    )

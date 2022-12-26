# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from frozendict import frozendict

from science.model import Distribution, File, Identifier


def test_distribution() -> None:
    distribution = Distribution(
        id=Identifier.parse("cpython"),
        file=File(
            name="cpython-3.9.14+20221002-x86_64-unknown-linux-gnu-install_only.tar.gz",
            key="cpython39",
        ),
        placeholders=frozendict(
            {
                Identifier.parse("python"): "python/bin/python",
                Identifier.parse("pip"): "python/bin/pip",
            }
        ),
    )

    assert "foo" == distribution.expand_placeholders("foo")
    assert "#{foo}" == distribution.expand_placeholders("#{foo}")
    assert "{cpython}" == distribution.expand_placeholders("{cpython}")
    assert "{cpython39}/arbitrary/path" == distribution.expand_placeholders(
        "#{cpython}/arbitrary/path"
    )
    assert "{cpython39}/python/bin/python" == distribution.expand_placeholders("#{cpython:python}")
    assert "{cpython39}/python/bin/pip" == distribution.expand_placeholders("#{cpython:pip}")

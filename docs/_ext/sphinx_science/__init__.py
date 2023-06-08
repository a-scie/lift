# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from typing import Any

from sphinx.application import Sphinx
from sphinx_science.dataclass import RenderDataclass
from sphinx_science.providers import RenderProviders


def setup(app: Sphinx) -> dict[str, Any]:
    RenderDataclass.register(app, "dataclass")
    RenderProviders.register(app, "providers")

    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }

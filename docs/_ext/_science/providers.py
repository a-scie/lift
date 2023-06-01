# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import itertools
from typing import Any, Iterator

from docutils import nodes
from docutils.parsers.rst import Directive
from sphinx import application

from science import providers
from science.providers import ProviderInfo


def _make_nodes(provider_info: ProviderInfo) -> Iterator[nodes.Node]:
    assert provider_info.short_name, "Expected all built-in providers to have short names defined."
    short_name = provider_info.short_name
    yield nodes.section(
        "",
        nodes.title(text=short_name),
        ids=[nodes.make_id(short_name)],
        names=[nodes.fully_normalize_name(short_name)],
    )

    yield nodes.paragraph()
    class_line = nodes.line()
    class_line.append(nodes.strong(text="class: "))
    class_line.append(nodes.literal(text=provider_info.fully_qualified_name))
    yield class_line

    if provider_info.summary:
        yield nodes.paragraph()
        yield nodes.strong(text=provider_info.summary)

        if provider_info.description:
            paragraph = list[str]()

            def maybe_add_paragraph() -> Iterator[nodes.Node]:
                if paragraph:
                    yield nodes.paragraph()
                    yield nodes.line(text="".join(paragraph))

            for line in provider_info.description.splitlines(keepends=True):
                if line.strip():
                    paragraph.append(line)
                else:
                    yield from maybe_add_paragraph()
                    paragraph.clear()

            yield from maybe_add_paragraph()


class _Providers(Directive):
    def run(self) -> list[nodes.Node]:
        return list(
            itertools.chain.from_iterable(
                _make_nodes(provider_info) for provider_info in providers.iter_builtin_providers()
            )
        )


def setup(app: application.Sphinx) -> dict[str, Any]:
    app.add_directive("providers", _Providers)

    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }

# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).
import itertools
from functools import cached_property
from typing import Any, Iterable, Iterator

from docutils import nodes
from docutils.parsers.rst import Directive
from markdown_it import MarkdownIt
from myst_parser.config.main import MdParserConfig
from myst_parser.mdit_to_docutils.base import DocutilsRenderer
from myst_parser.parsers.mdit import create_md_parser
from sphinx import application

from science import providers
from science.providers import ProviderInfo


class _Providers(Directive):
    @cached_property
    def _markdown_parser(self) -> MarkdownIt:
        return create_md_parser(MdParserConfig(), DocutilsRenderer)

    def _parse_markdown(self, text: str) -> Iterable[nodes.Node]:
        return self._markdown_parser.render(text).children

    def _make_nodes(self, provider_info: ProviderInfo) -> Iterator[nodes.Node]:
        assert (
            provider_info.short_name
        ), "Expected all built-in providers to have short names defined."
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
            summary = nodes.strong()
            summary.extend(self._parse_markdown(provider_info.summary))
            yield summary

            if provider_info.description:
                yield from self._parse_markdown(provider_info.description)

    def run(self) -> list[nodes.Node]:
        return list(
            itertools.chain.from_iterable(
                self._make_nodes(provider_info)
                for provider_info in providers.iter_builtin_providers()
            )
        )


def setup(app: application.Sphinx) -> dict[str, Any]:
    app.add_directive("providers", _Providers)

    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }

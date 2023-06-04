# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Iterable, Self

from docutils import nodes
from docutils.parsers.rst import Directive
from markdown_it import MarkdownIt
from myst_parser.config.main import MdParserConfig
from myst_parser.mdit_to_docutils.base import DocutilsRenderer
from myst_parser.parsers.mdit import create_md_parser
from sphinx import application

from science import providers
from science.providers import ProviderInfo


@dataclass
class Section:
    @classmethod
    def create(cls, *, title: str, name: str | None = None) -> Self:
        identifier = name or title
        section = nodes.section(
            "",
            nodes.title(text=title),
            ids=[nodes.make_id(identifier)],
            names=[nodes.fully_normalize_name(identifier)],
        )
        return cls(identifier=identifier, node=section)

    identifier: str
    node: nodes.Element

    def append(self, child: nodes.Node) -> None:
        self.node.append(child)

    def extend(self, children: Iterable[nodes.Node]) -> None:
        self.node.extend(children)

    def create_subsection(self, *, title: str, name: str | None = None) -> Self:
        subsection = self.create(title=title, name=f"{self.identifier}.{name or title}")
        self.append(subsection.node)
        return subsection


class _Providers(Directive):
    @cached_property
    def _markdown_parser(self) -> MarkdownIt:
        return create_md_parser(MdParserConfig(enable_extensions={"linkify"}), DocutilsRenderer)

    def _parse_markdown(self, text: str) -> Iterable[nodes.Node]:
        return self._markdown_parser.render(text).children

    def _make_node(self, provider_info: ProviderInfo) -> nodes.Node:
        assert (
            provider_info.short_name
        ), "Expected all built-in providers to have short names defined."
        provider_section = Section.create(title=provider_info.short_name)

        if provider_info.summary:
            description = f"**{provider_info.summary}**"
            if provider_info.description:
                description = os.linesep.join((description, "", provider_info.description))
            provider_section.extend(self._parse_markdown(description))

        for field_info in provider_info.iter_config_fields():
            field_section = provider_section.create_subsection(title=field_info.name)

            default = f" [default: `{field_info.default!r}`]" if field_info.has_default else ""
            field_section.extend(self._parse_markdown(f"*type: `{field_info.type}`{default}*"))

            if field_info.help:
                field_section.extend(self._parse_markdown(field_info.help))

        return provider_section.node

    def run(self) -> list[nodes.Node]:
        return [
            self._make_node(provider_info) for provider_info in providers.iter_builtin_providers()
        ]


def setup(app: application.Sphinx) -> dict[str, Any]:
    app.add_directive("providers", _Providers)

    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }

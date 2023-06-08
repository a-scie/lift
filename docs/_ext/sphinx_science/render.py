# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cached_property
from typing import Iterable, Self, final

from docutils import nodes
from docutils.parsers.rst import Directive
from markdown_it import MarkdownIt
from myst_parser.config.main import MdParserConfig
from myst_parser.mdit_to_docutils.base import DocutilsRenderer
from myst_parser.parsers.mdit import create_md_parser


@dataclass
class Section:
    @classmethod
    def create(cls, *, title: str, name: str = "") -> Self:
        section = nodes.section(
            "",
            nodes.title(text=title),
            ids=[nodes.make_id(name)],
            names=[nodes.fully_normalize_name(name)],
        )
        return cls(name=name, node=section)

    name: str
    node: nodes.Element

    def append(self, child: nodes.Node) -> None:
        self.node.append(child)

    def extend(self, children: Iterable[nodes.Node]) -> None:
        self.node.extend(children)

    def create_subsection(self, *, title: str, name: str = "") -> Self:
        subsection = self.create(title=title, name=f"{self.name}.{name}")
        self.append(subsection.node)
        return subsection


class MarkdownParser:
    ENABLE_EXTENSIONS = ["linkify"]

    @cached_property
    def _markdown_parser(self) -> MarkdownIt:
        return create_md_parser(
            MdParserConfig(enable_extensions=set(self.ENABLE_EXTENSIONS)), DocutilsRenderer
        )

    @final
    def parse_markdown(self, text: str) -> Iterable[nodes.Node]:
        document = self._markdown_parser.render(text, env={})
        return document.children


class MarkdownDirective(MarkdownParser, Directive, ABC):
    @abstractmethod
    def run(self) -> list[nodes.Node]:
        pass

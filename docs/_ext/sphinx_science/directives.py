# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint
from pathlib import Path
from textwrap import dedent
from typing import Iterable, Iterator, Mapping, NewType

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from docutils.statemachine import StringList
from sphinx import addnodes
from sphinx.application import Sphinx
from sphinx.environment import BuildEnvironment

from science.frozendict import FrozenDict

Id = NewType("Id", str)


def type_id(type_: type) -> Id:
    return Id(nodes.make_id(f"{type_.__module__}.{type_.__qualname__}"))


def create_type_reference(type_: type) -> str:
    return f"{type_.__module__}:{type_.__qualname__}"


def parse_type_reference(type_reference: str) -> type:
    return EntryPoint(name="", group="", value=type_reference).load()


def serialize_bool_option(value: bool) -> str:
    return "yes" if value else "no"


def bool_option(default: bool = False):
    def parse_option(argument: str | None) -> bool:
        sanitized = (argument or serialize_bool_option(default)).strip().lower()
        match sanitized:
            case "yes":
                return True
            case "no":
                return False

        raise ValueError(
            f"Boolean option requires a (case-insensitive) value of 'yes' or 'no'}}, "
            f"got: {argument}"
        )

    return parse_option


@dataclass(frozen=True)
class DirectiveSpec:
    name: str
    args: tuple[str, ...] = ()
    options: Mapping[str, str] = FrozenDict()
    content: StringList = field(default_factory=StringList)

    def render_markdown(self) -> str:
        content_items = [f"```{{{self.name}}} {" ".join(self.args)}"]
        for key, val in self.options.items():
            if val is not None:
                if isinstance(val, bool):
                    content_items.append(f":{key}: {serialize_bool_option(val)!r}")
                else:
                    content_items.append(f":{key}: {val}")
        if self.content:
            content_items.extend(self.content)
        content_items.append("```")
        return "\n".join(content_items)


@dataclass(frozen=True)
class Doc:
    id: Id
    name: str
    directive: DirectiveSpec

    def write(self, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{self.name}.md"
        path.write_text(
            dedent(
                """\
                ({id})=
                {directive}
                """
            ).format(id=self.id, directive=self.directive.render_markdown())
        )
        return path


class DocGen(ABC):
    @classmethod
    @abstractmethod
    def enumerate_docs(cls, directive_spec: DirectiveSpec) -> Iterator[Doc]:
        pass


class DocGenDirective(DocGen, Directive):
    @classmethod
    def register(cls, app: Sphinx, name: str) -> None:
        _MultiDocGen.register(app, name, cls)

    @abstractmethod
    def run(self) -> list[nodes.Node]:
        pass


class _GenNode(nodes.General, nodes.Element):
    pass


@dataclass(frozen=True)
class _MultiDocGen:
    @classmethod
    def register(
        cls, app: Sphinx, directive_name: str, doc_gen_directive: type[DocGenDirective]
    ) -> None:
        doc_gen_directive_name = f"{directive_name}-content"
        app.add_directive(name=doc_gen_directive_name, cls=doc_gen_directive)

        out_dir = Path(app.srcdir) / "_"
        shutil.rmtree(out_dir, ignore_errors=True)

        generated_for = dict[Path, addnodes.toctree]()

        class Synthesized(Directive):
            has_content = getattr(doc_gen_directive, "has_content", False)
            option_spec = {
                **getattr(doc_gen_directive, "option_spec", {}),
                "toctree_hidden": directives.flag,
                "toctree_maxdepth": directives.positive_int,
            }
            required_arguments = getattr(doc_gen_directive, "required_arguments", 0)
            optional_arguments = getattr(doc_gen_directive, "optional_arguments", 0)

            def run(self) -> list[nodes.Node]:
                assert self.state.document.current_source is not None, (
                    f"We always expect documents we handle to have a source. "
                    f"This document does not: {self.state.document}"
                )
                source = Path(self.state.document.current_source)
                if generated_toc_node := generated_for.get(source):
                    # N.B.: We use the `env-get-outdated` event below to manually read doctrees
                    # behind the back of Sphinx which triggers this directive the 1st time and
                    # generates new docs files that we tell Sphinx about in that event (by mutating
                    # `added`). Later in the Sphinx life-cycle, it does its own read of all known
                    # doctrees triggering this directive a second time. On the second time around we
                    # want to skip the generation process.
                    return [generated_toc_node]

                dest_dir = out_dir / source.relative_to(app.srcdir).with_suffix("")
                dest_dir.mkdir(parents=True, exist_ok=True)

                toctree_maxdepth = self.options.pop("toctree_maxdepth", None)
                toctree_hidden = "toctree_hidden" in self.options
                if toctree_hidden:
                    self.options.pop("toctree_hidden")

                docnames = tuple(
                    str(doc.write(dest_dir).relative_to(app.srcdir).with_suffix(""))
                    for doc in doc_gen_directive.enumerate_docs(
                        DirectiveSpec(
                            name=doc_gen_directive_name,
                            args=tuple(self.arguments),
                            options=FrozenDict(self.options),
                            content=self.content,
                        )
                    )
                )

                gen_node = _GenNode()
                gen_node["docnames"] = docnames

                toc_node = addnodes.toctree()
                toc_node["glob"] = False
                toc_node["hidden"] = toctree_hidden
                if toctree_maxdepth:
                    toc_node["maxdepth"] = toctree_maxdepth
                toc_node["includefiles"] = docnames

                # These are (title, ref) pairs, where ref can be a document or an external link,
                # and title can be None if the document's title should be used.
                toc_node["entries"] = [(None, docname) for docname in docnames]

                generated_for[source] = toc_node
                return [gen_node, toc_node]

        app.add_directive(name=directive_name, cls=Synthesized)

        def env_get_outdated(
            _app: Sphinx, env: BuildEnvironment, added: set[str], changed: set[str], *_ignored
        ) -> Iterable[str]:
            for docname in added | changed:
                app.builder.read_doc(docname)
                for gen_node in env.get_doctree(docname).findall(_GenNode):
                    added.update(gen_node["docnames"])
            return ()

        app.connect("env-get-outdated", env_get_outdated)

        def doctree_resolved(_app: Sphinx, doctree: nodes.document, _docname: str) -> None:
            for gen_node in doctree.findall(_GenNode):
                gen_node.replace_self([])

        app.connect("doctree-resolved", doctree_resolved)

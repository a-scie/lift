# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
from typing import Iterator

from docutils import nodes
from sphinx_science.directives import DirectiveSpec, Doc, DocGenDirective, type_id
from sphinx_science.render import MarkdownParser, Section
from sphinx_science.toml import TOMLTypeRenderer

from science import providers
from science.frozendict import FrozenDict
from science.providers import ProviderInfo


class RenderProviders(MarkdownParser, DocGenDirective):
    @classmethod
    def enumerate_docs(cls, directive_spec: DirectiveSpec) -> Iterator[Doc]:
        options = FrozenDict(
            {**directive_spec.options, **TOMLTypeRenderer.create_options(recurse_tables=False)}
        )

        for provider_info in providers.iter_builtin_providers():
            slug = provider_info.short_name or provider_info.fully_qualified_name
            yield Doc(
                id=type_id(provider_info.type),
                name=slug,
                directive=dataclasses.replace(
                    directive_spec,
                    args=tuple([provider_info.fully_qualified_name]),
                    options=options,
                ),
            )

    optional_arguments = 1
    option_spec = {
        **TOMLTypeRenderer.OPTION_SPEC,
    }
    has_content = False

    def render_provider(
        self, provider_info: ProviderInfo, toml_type_renderer: TOMLTypeRenderer
    ) -> nodes.Node:
        assert (
            provider_info.short_name
        ), "Expected all built-in providers to have short names defined."
        provider_section = Section.create(title=provider_info.short_name)

        if provider_info.summary:
            description = f"**{provider_info.summary}**"
            if provider_info.description:
                description = "\n".join((description, "", provider_info.description))
            provider_section.extend(self.parse_markdown(description))

        for field_info in provider_info.config_fields():
            if field_info.hidden:
                continue
            field_section = provider_section.create_subsection(
                title=field_info.name, name=field_info.name
            )
            field_section.extend(
                toml_type_renderer.render_field(
                    field_info, owner=provider_info.type.config_dataclass()
                )
            )

        return provider_section.node

    def run(self) -> list[nodes.Node]:
        provider_info = providers.get_provider(provider := self.arguments[0])
        if not provider_info:
            raise self.error(f"No Provider with id {provider!r} is registered.")
        toml_type_renderer = TOMLTypeRenderer.from_options(self.options)
        return [self.render_provider(provider_info, toml_type_renderer)]

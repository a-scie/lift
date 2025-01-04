# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import dataclasses
from typing import Iterator, cast

from docutils import nodes

from science.dataclass import Dataclass
from science.dataclass.reflect import DataclassInfo, iter_dataclass_info
from science.frozendict import FrozenDict
from sphinx_science import directives
from sphinx_science.directives import (
    DirectiveSpec,
    Doc,
    DocGenDirective,
    create_type_reference,
    parse_type_reference,
)
from sphinx_science.toml import TOMLTypeRenderer


class RenderDataclass(DocGenDirective):
    @staticmethod
    def check_dataclass(data_type: type) -> type[Dataclass]:
        if not dataclasses.is_dataclass(data_type):
            raise TypeError(
                "Can only render for dataclasses. Resolved non-dataclass: "
                f"{data_type.__module__}.{data_type.__qualname__}"
            )
        return cast(type[Dataclass], data_type)

    @classmethod
    def enumerate_docs(cls, directive_spec: DirectiveSpec) -> Iterator[Doc]:
        dataclass_entrypoint = cls.check_dataclass(parse_type_reference(directive_spec.args[0]))

        options = FrozenDict(
            {**directive_spec.options, **TOMLTypeRenderer.create_options(recurse_tables=False)}
        )

        def doc(type_info: DataclassInfo) -> Doc:
            return Doc(
                id=directives.type_id(type_info.type),
                name=type_info.name,
                directive=dataclasses.replace(
                    directive_spec,
                    args=tuple([create_type_reference(type_info.type)]),
                    options=options,
                ),
            )

        seen = set[DataclassInfo]()
        for data_type_info in iter_dataclass_info(
            dataclass_entrypoint, include_hidden=False, include_inlined=False
        ):
            if data_type_info in seen:
                continue
            seen.add(data_type_info)
            yield doc(data_type_info)

    required_arguments = 1
    option_spec = {
        **TOMLTypeRenderer.OPTION_SPEC,
    }
    has_content = False

    def run(self) -> list[nodes.Node]:
        dataclass_entrypoint = self.check_dataclass(parse_type_reference(self.arguments[0]))
        renderer = TOMLTypeRenderer.from_options(self.options)
        return [*renderer.render_dataclass(dataclass_entrypoint)]

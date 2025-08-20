# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass, field
from typing import Any, Callable

import click


def to_option_string(word: str) -> str:
    return f"--{word.replace('_', '-')}"


@dataclass(frozen=True)
class OptionDescriptor:
    name: str
    flag: str = field(default="", kw_only=True)

    def __post_init__(self) -> None:
        if not self.flag:
            object.__setattr__(self, "flag", to_option_string(self.name))


def mutually_exclusive(
    option1: str | OptionDescriptor,
    option2: str | OptionDescriptor,
    /,
    *other_options: str | OptionDescriptor,
) -> Callable[[click.Context, click.Parameter, Any], None]:
    options = tuple(
        option if isinstance(option, OptionDescriptor) else OptionDescriptor(option)
        for option in (option1, option2, *other_options)
    )

    def check_mutually_exclusive(ctx: click.Context, param: click.Parameter, value: Any) -> Any:
        if not value:
            return value

        others = [
            option.flag
            for option in options
            if option.name != param.name and option.name in ctx.params
        ]
        if others:
            head = ", ".join(option.flag for option in options[:-1])
            tail = options[-1].flag
            raise click.BadParameter(
                f"Can only specify one of {head} or {tail}. Already specified {' '.join(others)}."
            )
        return value

    return check_mutually_exclusive

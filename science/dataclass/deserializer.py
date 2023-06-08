# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

import dataclasses
import os
import typing
from collections import OrderedDict
from textwrap import dedent
from typing import Any, Collection, Mapping, TypeVar, cast

from science.data import Data
from science.dataclass import Dataclass
from science.errors import InputError
from science.frozendict import FrozenDict
from science.types import TypeInfo

_F = TypeVar("_F")


def _parse_field(
    name: str,
    type_: TypeInfo[_F],
    default: _F | Data.Required,
    data: Data,
    custom_parsers: Mapping[type, typing.Callable[[Data], Any]],
) -> _F:
    if type_.has_origin_type and (parser := custom_parsers.get(type_.origin_type)):
        return parser(data)

    if dataclass_type := type_.dataclass:
        data_value = data.get_data(
            name,
            default=cast(
                dict[str, Any] | Data.Required,
                (
                    dataclasses.asdict(default)  # type: ignore[arg-type]
                    if dataclasses.is_dataclass(default)
                    else default
                ),
            ),
        )
        return cast(_F, parse(data_value, dataclass_type, custom_parsers=custom_parsers))

    if type_.istype(int):
        return cast(_F, data.get_int(name, default=cast(int | Data.Required, default)))
    if type_.istype(float):
        return cast(_F, data.get_float(name, default=cast(float | Data.Required, default)))
    if type_.istype(str):
        return cast(_F, data.get_str(name, default=cast(str | Data.Required, default)))
    if type_.istype(bool):
        return cast(_F, data.get_bool(name, default=cast(bool | Data.Required, default)))

    if map_type := type_.issubtype(Mapping):
        # default is Env
        data_value = data.get_data(name, default=cast(dict[str, Any] | Data.Required, default))
        # We assume any mapping type used will be constructible with a single dict argument.
        return cast(_F, map_type(data_value.data))

    if type_.issubtype(Collection) and not type_.issubtype(str):
        item_type = type_.item_type
        if dataclasses.is_dataclass(item_type) or isinstance(item_type, Mapping):
            data_list = data.get_data_list(name, default=cast(list | Data.Required, default))
            if isinstance(item_type, Mapping):
                return cast(
                    _F,
                    [
                        # We assume any mapping type used will be constructible with a single dict
                        # argument.
                        cast(Mapping, item_type(data_item.data))  # type: ignore[misc]
                        for data_item in data_list
                    ],
                )
            else:
                return cast(
                    _F,
                    [
                        parse(data_item, item_type, custom_parsers=custom_parsers)
                        for data_item in data_list
                    ],
                )
        else:
            return cast(
                _F,
                data.get_list(
                    name, expected_item_type=item_type, default=cast(list | Data.Required, default)
                ),
            )

    value = data.get_value(name, expected_type=object, default=default)
    if value is default:
        return cast(_F, value)

    # As a last resort, see if the value is convertible to type via its constructor. This supports
    # Enum and similar types.
    try:
        return type_.origin_type(value)  # type: ignore[call-arg]
    except (TypeError, ValueError) as e:
        raise InputError(
            dedent(
                f"""\
                The field {data.config(name)} is of type {type_} which was not parseable:
                    {e}

                You must use one of the following:
                + int
                + float
                + str
                + bool
                + A dataclass
                + A collection type like list, tuple, set or frozenset
                + A mapping type like dict or FrozenDict
                + A type that has a single argument constructor accepting one of the above.
                """
            ).strip()
        )


_D = TypeVar("_D", bound=Dataclass)


def parse(
    data,
    data_type: type[_D],
    *,
    custom_parsers: Mapping[type, typing.Callable[[Data], Any]] = FrozenDict(),
    **pre_parsed_fields: Any,
) -> _D:
    if not dataclasses.is_dataclass(data_type):
        raise InputError(f"Cannot parse data_type {data_type}, it is not a @dataclass.")

    if parser := custom_parsers.get(data_type):
        return parser(data)

    type_hints = typing.get_type_hints(data_type)

    def get_type(field_name: str, putative_type: Any) -> TypeInfo:
        if isinstance(putative_type, type):
            return TypeInfo(putative_type)
        try:
            return TypeInfo(type_hints[field_name])
        except KeyError:
            raise InputError(
                f"Failed to reify {putative_type} of type {type(putative_type)} into a type."
            )

    kwargs = {}
    for field in dataclasses.fields(data_type):
        if value := pre_parsed_fields.get(field.name):
            kwargs[field.name] = value
            continue

        type_info = get_type(field_name=field.name, putative_type=field.type)
        if type_info.optional:
            kwargs[field.name] = None

        errors = OrderedDict[TypeInfo, Exception]()
        for field_type in type_info.iter_types():

            def parse_field(data: Data) -> Any:
                return _parse_field(
                    name=field.name,
                    type_=field_type,
                    default=(
                        field.default if field.default is not dataclasses.MISSING else Data.REQUIRED
                    ),
                    data=data,
                    custom_parsers=custom_parsers,
                )

            parser = custom_parsers.get(field_type.origin_type, parse_field)
            try:
                kwargs[field.name] = parser(data)
                break
            except (TypeError, ValueError, InputError) as e:
                errors[field_type] = e

        if field.name not in kwargs:
            raise InputError(
                dedent(
                    """\
                    Failed to parse {config}.

                    Tried:
                    {attempts}
                    """
                ).format(
                    config=data.config(field.name),
                    attempts=os.linesep.join(
                        f"{field_type}: {error}" for field_type, error in errors.items()
                    ),
                )
            )

    return cast(_D, data_type(**kwargs))

# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import copy
from typing import Generic, Iterator, Mapping, TypeVar

K = TypeVar("K")
V = TypeVar("V", covariant=True)


class FrozenDict(Generic[K, V], Mapping[K, V]):
    def __init__(self, data: Mapping[K, V] | None = None) -> None:
        super().__init__()
        self._data: Mapping[K, V] = copy.deepcopy(data) if data else {}
        self._hash: int | None = None

    def __getitem__(self, key: K) -> V:
        return self._data[key]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[K]:
        return iter(self._data)

    def __eq__(self, o: object) -> bool:
        return isinstance(o, FrozenDict) and self._data == o._data

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(tuple(self.items()))
        return self._hash

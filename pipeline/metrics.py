"""Metric registry for stage 8.

A Metric is a pure function of the database (plus the working-set labels): the same
state gives the same numbers. That is what lets the mutation tests (pipeline.mutations)
apply a known fault to a scratch copy and see whether the number moves.
"""

import sqlite3
from dataclasses import dataclass
from typing import Callable

# subject -> value; the empty subject means "overall".
Values = dict[str, float]


@dataclass(frozen=True)
class Metric:
    layer: str
    name: str
    compute: Callable[[sqlite3.Connection], Values]
    doc: str = ""

    @property
    def key(self) -> str:
        return f"{self.layer}.{self.name}"


REGISTRY: list[Metric] = []

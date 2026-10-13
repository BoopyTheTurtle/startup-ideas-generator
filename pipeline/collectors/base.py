"""Base class every stream collector extends.

A collector yields Items; the runner (pipeline.collect) stores them, hashes authors,
deduplicates, updates health, and logs metrics. Collectors never touch the database.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pipeline.http import Http


class SchemaDrift(RuntimeError):
    """The source's response no longer has the shape the collector expects."""


def require(obj: Any, keys: list[str], where: str) -> None:
    """Fail loudly when an undocumented API changes shape."""
    if not isinstance(obj, dict):
        raise SchemaDrift(f"{where}: expected object, got {type(obj).__name__}")
    missing = [k for k in keys if k not in obj]
    if missing:
        raise SchemaDrift(f"{where}: missing keys {missing}")


@dataclass
class Item:
    source_id: str
    body: str
    url: str | None = None
    title: str | None = None
    author: str | None = None         # hashed by the runner, never stored raw
    created_at: str | None = None     # UTC ISO 8601
    lang: str | None = None           # ISO 639-1
    country: str | None = None        # ISO 3166-1 alpha-2, or 'EU'
    metrics: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    # Per-item overrides for collectors whose items come from several sites (forums).
    license: str | None = None
    tos_class: str | None = None


class State:
    """Small key-value store per collector, persisted between runs."""

    def __init__(self, values: dict[str, str]):
        self.values = dict(values)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


class Collector(ABC):
    name: ClassVar[str]                # short id, also the fixtures folder name
    license: ClassVar[str]             # e.g. 'OGL-3.0', 'CC-BY-SA-4.0', 'API terms'
    tos_class: ClassVar[str]           # clean, gray, restricted
    regions: ClassVar[list[str]]       # countries or 'EU'/'GLOBAL' this source covers
    min_interval: ClassVar[float] = 1.0  # seconds between requests

    def __init__(self, max_items: int = 500):
        self.max_items = max_items
        # Problems with one part of a run (a forum, a site) that did not stop the rest.
        # A run with warnings ends 'partial', or 'failed' when every unit failed.
        self.warnings: list[str] = []
        self.units_ok: list[str] = []
        self.units_failed: list[str] = []

    def guarded(self, unit: str, items: Iterable[Item]) -> Iterator[Item]:
        """Yield from one unit (a forum, a plugin), turning its failure into a warning
        so the other units still run. The runner tracks a failure streak per unit."""
        try:
            yield from items
        except Exception as e:  # noqa: BLE001 — isolation is the point
            self.units_failed.append(unit)
            self.warnings.append(f"{unit}: {type(e).__name__}: {str(e)[:200]}")
            return
        self.units_ok.append(unit)

    @abstractmethod
    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        """Yield new items, newest first or oldest first, up to self.max_items.

        Read and update cursors through `state`; the runner persists them only when
        the run succeeds.
        """

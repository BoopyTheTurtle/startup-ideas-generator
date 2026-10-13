"""Stream collectors. Each module defines one Collector subclass; discovery is automatic."""

import importlib
import pkgutil

from pipeline.collectors.base import Collector


def discover() -> dict[str, type[Collector]]:
    found: dict[str, type[Collector]] = {}
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_") or mod.name == "base":
            continue
        module = importlib.import_module(f"{__name__}.{mod.name}")
        for obj in vars(module).values():
            if (isinstance(obj, type) and issubclass(obj, Collector)
                    and obj is not Collector and getattr(obj, "name", None)
                    and obj.__module__ == module.__name__):
                found[obj.name] = obj
    return dict(sorted(found.items()))

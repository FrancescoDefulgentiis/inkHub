"""Module factory / registry.

Modules register themselves via the :func:`register_module` decorator. The
:func:`create_module` factory then instantiates them by name, so the main
app never needs to import concrete module classes directly.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any, Mapping

from .module import Module

_log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[Module]] = {}


def register_module(name: str):
    """Class decorator that adds a :class:`Module` subclass to the registry.

    :param name: Unique short name used in ``config.json`` (``active_module``).
    """

    def decorator(cls: type[Module]) -> type[Module]:
        if not issubclass(cls, Module):
            raise TypeError(f"{cls!r} must subclass Module")
        if name in _REGISTRY:
            raise ValueError(f"Module {name!r} is already registered")
        cls.name = name
        _REGISTRY[name] = cls
        _log.debug("Registered module %r -> %s", name, cls.__name__)
        return cls

    return decorator


def discover_modules() -> None:
    """Import every submodule of ``inkhub.modules`` so decorators run."""
    from . import modules as _modules_pkg

    for info in pkgutil.iter_modules(_modules_pkg.__path__):
        importlib.import_module(f"{_modules_pkg.__name__}.{info.name}")


def create_module(
    name: str,
    config: Mapping[str, Any],
    size: tuple[int, int],
) -> Module:
    """Instantiate a registered module by name.

    :param name: Name used with :func:`register_module`.
    :param config: The module's config block from ``config.json``.
    :param size: ``(width, height)`` of the e-ink panel.
    :raises KeyError: if no module with that name is registered.
    """
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown module {name!r}. Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name](config, size)


def available_modules() -> list[str]:
    """Return the sorted list of registered module names."""
    return sorted(_REGISTRY)

"""Module factory / registry.

Modules register themselves via the :func:`register_module` decorator. The
:func:`create_module` factory then instantiates them by name, so the main
app never needs to import concrete module classes directly.

Each module folder is expected to ship a ``config.json`` next to its
``__init__.py``. That file is the *only* place module-specific settings live
— the root ``src/config.json`` no longer stores per-module blocks.
This makes modules drag-and-drop: copy a folder into ``src/modules/`` and
its configuration comes along with it.
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import pkgutil
from pathlib import Path
from typing import Any

from .module import Module

_log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[Module]] = {}

#: File name each module folder may contain for its own settings.
MODULE_CONFIG_FILENAME = "config.json"


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


def module_folder(name: str) -> Path:
    """Return the on-disk folder for a registered module.

    :raises KeyError: if no module with that name is registered.
    """
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown module {name!r}. Available: {sorted(_REGISTRY)}"
        )
    cls = _REGISTRY[name]
    return Path(inspect.getfile(cls)).resolve().parent


def load_module_config(name: str) -> dict[str, Any]:
    """Load ``<module_folder>/config.json`` for a registered module.

    Returns an empty dict if the file is missing. Malformed JSON is logged
    and treated as empty so a broken config never crashes the app.

    :raises KeyError: if no module with that name is registered.
    """
    cfg_path = module_folder(name) / MODULE_CONFIG_FILENAME
    if not cfg_path.is_file():
        return {}
    try:
        with cfg_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning(
            "Ignoring invalid module config for %r at %s: %s",
            name, cfg_path, exc,
        )
        return {}
    if not isinstance(data, dict):
        _log.warning(
            "Module config for %r at %s is not a JSON object; ignoring",
            name, cfg_path,
        )
        return {}
    return data


def create_module(name: str, size: tuple[int, int]) -> Module:
    """Instantiate a registered module by name.

    The module's configuration is loaded from ``<module_folder>/config.json``
    automatically — callers no longer need to slice a shared config dict.

    :param name: Name used with :func:`register_module`.
    :param size: ``(width, height)`` of the e-ink panel.
    :raises KeyError: if no module with that name is registered.
    """
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown module {name!r}. Available: {sorted(_REGISTRY)}"
        )
    config = load_module_config(name)
    return _REGISTRY[name](config, size)


def available_modules() -> list[str]:
    """Return the sorted list of registered module names."""
    return sorted(_REGISTRY)

"""Runtime "show diagnostics" toggle.

Owns a single boolean flag that gates verbose logging. When the flag is ON the
root logger runs at the configured *verbose* level (typically the ``log_level``
from ``config.json``, e.g. ``INFO`` or ``DEBUG``); when it is OFF the root
logger is raised to the configured *quiet* level (``WARNING`` by default) so
the console stays clean.

The launcher menu toggles this flag when the user presses ``D``.
"""

from __future__ import annotations

import logging
import threading

_lock = threading.Lock()
_enabled: bool = False
_verbose_level: int = logging.INFO
_quiet_level: int = logging.WARNING


def configure(
    verbose_level: int = logging.INFO,
    quiet_level: int = logging.WARNING,
) -> None:
    """Set the log levels used when the flag is ON / OFF and apply them.

    Safe to call at any time; the current flag state is preserved.
    """
    global _verbose_level, _quiet_level
    with _lock:
        _verbose_level = verbose_level
        _quiet_level = quiet_level
        _apply_locked()


def is_enabled() -> bool:
    """Return the current state of the diagnostics flag."""
    with _lock:
        return _enabled


def set_enabled(enabled: bool) -> bool:
    """Force the diagnostics flag to *enabled*. Returns the new state."""
    global _enabled
    with _lock:
        _enabled = bool(enabled)
        _apply_locked()
        return _enabled


def toggle() -> bool:
    """Flip the diagnostics flag and update logging. Returns the new state."""
    global _enabled
    with _lock:
        _enabled = not _enabled
        _apply_locked()
        return _enabled


def _apply_locked() -> None:
    """Apply the current flag to the root logger (caller must hold _lock)."""
    logging.getLogger().setLevel(_verbose_level if _enabled else _quiet_level)

"""Physical button handling using ``gpiozero``.

Four momentary buttons wired to BCM pins from ``config.json`` (by default
5/6/13/19), pulled up, active-low. Presses are debounced and delivered to a
single callback with the button's zero-based index.
"""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from gpiozero import Button

_log = logging.getLogger(__name__)


class ButtonPanel:
    """Wire up N buttons and forward presses to a single callback."""

    def __init__(
        self,
        pins: Sequence[int],
        on_press: Callable[[int], None],
        pull_up: bool = True,
        bounce_time_ms: int = 50,
    ) -> None:
        """Register the buttons.

        :param pins: BCM GPIO pin numbers, in the order the caller will
            receive as ``index`` in ``on_press``.
        :param on_press: Callable invoked as ``on_press(index)`` on release.
        :param pull_up: ``True`` for active-low buttons wired to GND.
        :param bounce_time_ms: Software debounce window in milliseconds.
        """
        self._callback = on_press
        bounce = max(0, bounce_time_ms) / 1000.0
        self._buttons: list[Button] = []
        for index, pin in enumerate(pins):
            btn = Button(pin, pull_up=pull_up, bounce_time=bounce)
            btn.when_released = self._make_handler(index)
            self._buttons.append(btn)
            _log.info("Button %d bound to BCM GPIO %d", index, pin)

    def _make_handler(self, index: int) -> Callable[[], None]:
        def _handler() -> None:
            _log.debug("Button %d pressed", index)
            try:
                self._callback(index)
            except Exception:
                _log.exception("Button %d callback failed", index)

        return _handler

    def close(self) -> None:
        """Release GPIO resources."""
        for btn in self._buttons:
            try:
                btn.close()
            except Exception:  # pragma: no cover
                _log.exception("Failed to close button on pin %d", btn.pin.number)
        self._buttons.clear()

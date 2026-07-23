"""Thin wrapper around the vendored ``waveshare_epd`` Python driver."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from PIL import Image

_log = logging.getLogger(__name__)
_boot_log = logging.getLogger("inkhub.boot")


class Display:
    """Wraps a ``waveshare_epd`` panel driver behind a tiny, stable API."""

    def __init__(self, driver_name: str) -> None:
        """Load and initialise the panel driver.

        :param driver_name: Python module name inside ``waveshare_epd``
            (for example ``"epd7in5"``).
        """

        self._driver_name = driver_name
        _boot_log.warning(
            "[BOOT][display] starting display setup (driver=%s)",
            driver_name,
        )
        _log.info("Loading e-paper driver waveshare_epd.%s", driver_name)
        _boot_log.warning(
            "[BOOT][display] importing waveshare_epd.%s",
            driver_name,
        )
        module = importlib.import_module(f"waveshare_epd.{driver_name}")
        _boot_log.warning("[BOOT][display] import completed")
        _boot_log.warning("[BOOT][display] creating EPD driver instance")
        self._epd: Any = module.EPD()
        _boot_log.warning("[BOOT][display] EPD driver instance created")
        _boot_log.warning("[BOOT][display] calling epd.init()")
        self._epd.init()
        _boot_log.warning("[BOOT][display] epd.init() completed")
        _boot_log.warning("[BOOT][display] calling epd.Clear()")
        self._epd.Clear()
        _boot_log.warning("[BOOT][display] epd.Clear() completed")

        raw_w, raw_h = int(self._epd.width), int(self._epd.height)
        self.width, self.height = raw_w, raw_h
        _boot_log.warning(
            "[BOOT][display] setup completed (size=%dx%d)",
            self.width,
            self.height,
        )
        _log.info("Panel ready: %dx%d", self.width, self.height)

    @property
    def size(self) -> tuple[int, int]:
        """Return ``(width, height)`` of the drawable canvas."""
        return self.width, self.height

    def show(self, image: Image.Image) -> None:
        """Push ``image`` to the panel (full refresh).

        Callers are responsible for rate-limiting: full refreshes take
        seconds and wear the panel.
        """
        buf = self._epd.getbuffer(image)
        self._epd.display(buf)

    def sleep(self) -> None:
        """Put the panel into low-power state (safe on shutdown)."""
        try:
            self._epd.sleep()
        except Exception:
            _log.exception("Failed to put display to sleep")

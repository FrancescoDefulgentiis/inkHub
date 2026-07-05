"""Thin wrapper around the vendored ``waveshare_epd`` Python driver.

The concrete panel driver module (e.g. ``epd7in5_V2``) is selected at runtime
from ``config.json`` so InkHub is not tied to a specific Waveshare panel.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from PIL import Image

_log = logging.getLogger(__name__)


class Display:
    """Wraps a ``waveshare_epd`` panel driver behind a tiny, stable API."""

    def __init__(self, driver_name: str, rotation: int = 0) -> None:
        """Load and initialise the panel driver.

        :param driver_name: Python module name inside ``waveshare_epd``
            (for example ``"epd7in5_V2"``).
        :param rotation: Extra rotation in degrees (0/90/180/270) applied to
            every rendered frame before it is pushed to the panel.
        """
        if rotation not in (0, 90, 180, 270):
            raise ValueError(f"rotation must be 0/90/180/270, got {rotation}")

        self._rotation = rotation
        self._driver_name = driver_name
        _log.info("Loading e-paper driver waveshare_epd.%s", driver_name)
        module = importlib.import_module(f"waveshare_epd.{driver_name}")
        self._epd: Any = module.EPD()
        self._epd.init()
        self._epd.Clear()

        # Panel dimensions are exposed as `width`/`height` on the EPD object.
        # After rotation the effective canvas swaps them for 90/270°.
        raw_w, raw_h = int(self._epd.width), int(self._epd.height)
        if rotation in (90, 270):
            self.width, self.height = raw_h, raw_w
        else:
            self.width, self.height = raw_w, raw_h
        _log.info("Panel ready: %dx%d (rotation=%d)", self.width, self.height, rotation)

    @property
    def size(self) -> tuple[int, int]:
        """Return ``(width, height)`` of the drawable canvas."""
        return self.width, self.height

    def new_frame(self) -> Image.Image:
        """Return a fresh 1-bit white canvas at the panel's size."""
        return Image.new("1", (self.width, self.height), 255)

    def show(self, image: Image.Image) -> None:
        """Push ``image`` to the panel (full refresh).

        Callers are responsible for rate-limiting: full refreshes take
        seconds and wear the panel.
        """
        if self._rotation:
            image = image.rotate(-self._rotation, expand=True)
        buf = self._epd.getbuffer(image)
        self._epd.display(buf)

    def sleep(self) -> None:
        """Put the panel into low-power state (safe on shutdown)."""
        try:
            self._epd.sleep()
        except Exception:  # pragma: no cover - hardware quirks
            _log.exception("Failed to put display to sleep")

"""Reference module: a plain digital clock.

Copy this file to build your own module — the two things that matter are the
``@register_module`` decorator and the :meth:`render` method.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

from ...module import Module
from ...registry import register_module

_log = logging.getLogger(__name__)


@register_module("clock")
class ClockModule(Module):
    """Displays the current time (large) and date (small), centred."""

    def __init__(self, config, size):
        super().__init__(config, size)
        self._time_format: str = self.config.get("time_format", "%H:%M")
        self._date_format: str = self.config.get("date_format", "%A, %d %B %Y")
        self._time_font = _load_font(max(48, self.height // 3))
        self._date_font = _load_font(max(18, self.height // 12))

    def next_update_delay(self) -> float:
        """Refresh exactly when the next minute begins."""
        now = datetime.now()
        next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        return max(0.0, (next_minute - now).total_seconds())

    def render(self) -> Image.Image:
        """Build the current time screen and return it."""
        now = datetime.now()
        time_text = now.strftime(self._time_format)
        date_text = now.strftime(self._date_format)
        image = self.new_image()
        draw = ImageDraw.Draw(image)

        tw, th = _text_size(draw, time_text, self._time_font)
        dw, dh = _text_size(draw, date_text, self._date_font)
        gap = max(8, self.height // 30)
        total_h = th + gap + dh
        y = (self.height - total_h) // 2

        draw.text(((self.width - tw) // 2, y), time_text, font=self._time_font, fill=0)
        draw.text(
            ((self.width - dw) // 2, y + th + gap),
            date_text,
            font=self._date_font,
            fill=0,
        )
        return image

def _load_font(size: int) -> ImageFont.ImageFont:
    """Try a common DejaVu path, fall back to Pillow's bundled default."""
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    _log.warning("DejaVu font not found, using Pillow default (small)")
    return ImageFont.load_default()

def _text_size(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont
) -> tuple[int, int]:
    """Return ``(width, height)`` occupied when drawing ``text`` at ``(x, y)``.

    ``draw.text((x, y), ...)`` places glyphs so their painted pixels span
    ``y + top`` .. ``y + bottom``. To stack two lines without overlap we need
    the full extent from ``y`` down to ``bottom``, not just the tight glyph
    box (``bottom - top``).
    """
    # Pillow >= 10 dropped ``textsize`` in favour of ``textbbox``.
    _, _, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right, bottom

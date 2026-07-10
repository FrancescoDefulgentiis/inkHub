"""Dashboard module: clock + weather summary + one inspirational quote per day.

This module rolls three things onto a single screen:

* **Clock** — large current time (``HH:MM``) with the date below.
* **Weather** — a compact view of Open-Meteo data (town, condition icon,
  current/feels-like temperature and a small stats strip: humidity, wind,
  sunrise, sunset). The networking, icon rendering and data containers used
  here live in the sibling :mod:`_weather <src.modules.dashboard._weather>`
  helper module.
* **Quote of the day** — one inspirational quote fetched from
  `ZenQuotes <https://zenquotes.io/>`_. The quote is refreshed **at most once
  per calendar day** and cached to disk, so switching to this module (or
  restarting the app) does not trigger a new fetch on the same day.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from ...module import Module
from ...registry import register_module
from ._weather import (
    Location,
    WeatherData,
    _draw_icon,
    _fetch_weather,
    _geocode,
    _hline,
    _load_font,
    _round_temp,
    _text_size,
    _weather_description,
    _weather_icon,
)

_log = logging.getLogger(__name__)

_QUOTE_URL = "https://zenquotes.io/api/today"
_HTTP_TIMEOUT = 15  # seconds
_WEATHER_MAX_AGE = timedelta(hours=1)

# Shown when we have never successfully fetched a quote (offline first-run).
_FALLBACK_QUOTE: tuple[str, str] = (
    "The best way to predict the future is to invent it.",
    "Alan Kay",
)


@dataclass
class Quote:
    """One inspirational quote plus the calendar day it was fetched."""

    text: str
    author: str
    fetched_on: date


@register_module("dashboard")
class DashboardModule(Module):
    """Clock + weather snapshot + one quote per day, all on the same screen."""

    def __init__(self, config, size):
        super().__init__(config, size)

        # --- Clock ---------------------------------------------------- #
        self._time_format: str = self.config.get("time_format", "%H:%M")
        self._date_format: str = self.config.get("date_format", "%A, %d %B %Y")

        # --- Weather -------------------------------------------------- #
        self._town: str = str(self.config.get("town", "London")).strip() or "London"
        self._country: str | None = (
            str(self.config["country"]).strip() if self.config.get("country") else None
        )
        self._temp_unit: str = str(self.config.get("temperature_unit", "celsius")).lower()
        self._wind_unit: str = str(self.config.get("wind_speed_unit", "kmh")).lower()

        # --- Quote ---------------------------------------------------- #
        self._quote_url: str = str(self.config.get("quote_url", _QUOTE_URL))
        cache_default = Path(".cache") / "dashboard_quote.json"
        self._quote_cache_path: Path = Path(
            str(self.config.get("quote_cache_path", cache_default))
        )

        # --- Cached state --------------------------------------------- #
        self._state_lock = threading.Lock()
        self._location: Location | None = None
        self._weather: WeatherData | None = None
        self._weather_error: str | None = None
        self._weather_fetched_at: datetime | None = None
        self._quote: Quote | None = self._load_cached_quote()

        # --- Fonts (scaled from panel height) ------------------------- #
        h = self.height
        self._font_time = _load_font(max(64, h // 6))
        self._font_date = _load_font(max(22, h // 20))
        self._font_temp = _load_font(max(40, h // 10))
        self._font_title = _load_font(max(24, h // 20))
        self._font_body = _load_font(max(20, h // 26))
        self._font_small = _load_font(max(16, h // 32))
        self._font_quote = _load_font(max(18, h // 28))
        self._font_quote_author = _load_font(max(14, h // 32))

    # ------------------------------------------------------------------ #
    # Scheduling                                                         #
    # ------------------------------------------------------------------ #
    def next_update_delay(self) -> float:
        """Refresh at the top of the next minute (for the clock)."""
        now = datetime.now()
        next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        return max(1.0, (next_minute - now).total_seconds())

    # ------------------------------------------------------------------ #
    # Rendering                                                          #
    # ------------------------------------------------------------------ #
    def render(self) -> Image.Image:
        """Fetch any stale data, then paint the three-section dashboard."""
        self._ensure_weather()
        self._ensure_quote()

        image = self.new_image()
        draw = ImageDraw.Draw(image)

        w, h = self.width, self.height
        margin = max(12, h // 40)

        # Vertical layout: clock ~26%, weather ~44%, quote ~30%.
        clock_bottom = margin + int(h * 0.26)
        quote_top = int(h * 0.70)

        self._draw_clock(draw, (margin, margin, w - margin, clock_bottom))
        _hline(draw, margin, clock_bottom, w - margin)
        self._draw_weather(
            draw,
            (margin, clock_bottom + margin // 2, w - margin, quote_top - margin // 2),
        )
        _hline(draw, margin, quote_top, w - margin)
        self._draw_quote(
            draw, (margin, quote_top + margin // 2, w - margin, h - margin),
        )
        return image

    # ---- Clock section ------------------------------------------------ #
    def _draw_clock(
        self, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        now = datetime.now()
        time_text = now.strftime(self._time_format)
        date_text = now.strftime(self._date_format)

        tw, th = _text_size(draw, time_text, self._font_time)
        dw, dh = _text_size(draw, date_text, self._font_date)
        gap = max(6, (y1 - y0) // 20)
        total_h = th + gap + dh
        y = y0 + max(0, ((y1 - y0) - total_h) // 2)
        cx = (x0 + x1) // 2

        draw.text((cx - tw // 2, y), time_text, font=self._font_time, fill=0)
        draw.text(
            (cx - dw // 2, y + th + gap), date_text, font=self._font_date, fill=0,
        )

    # ---- Weather section --------------------------------------------- #
    def _draw_weather(
        self, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        w = x1 - x0
        h = y1 - y0

        if self._weather is None:
            self._draw_weather_placeholder(draw, box)
            return

        data = self._weather
        cur = data.current
        temp_unit = data.units.get("temperature", "\u00b0C")
        wind_unit = data.units.get("wind_speed", "km/h")

        # Title row: location on the left, "updated HH:MM" on the right.
        title = data.location.name
        if data.location.country:
            title = f"{title}, {data.location.country}"
        subtitle = data.fetched_at.strftime("Updated %H:%M")
        _, title_h = _text_size(draw, title, self._font_title)
        sub_w, sub_h = _text_size(draw, subtitle, self._font_small)
        draw.text((x0, y0), title, font=self._font_title, fill=0)
        draw.text(
            (x1 - sub_w, y0 + max(0, (title_h - sub_h) // 2)),
            subtitle,
            font=self._font_small,
            fill=0,
        )

        # Split remaining vertical space into a title row and a content
        # row laid out horizontally: icon | temperature block | stats grid.
        content_top = y0 + title_h + max(4, h // 30)
        content_bottom = y1
        row_h = max(1, content_bottom - content_top)

        temp_text = f"{_round_temp(cur.temperature)}{temp_unit}"
        cond_text = _weather_description(cur.weather_code)
        feels_text = f"Feels like {_round_temp(cur.feels_like)}{temp_unit}"

        tw, th = _text_size(draw, temp_text, self._font_temp)
        cw, ch = _text_size(draw, cond_text, self._font_title)
        fw, fh = _text_size(draw, feels_text, self._font_body)
        info_gap = max(4, h // 40)
        info_h = th + info_gap + ch + info_gap + fh

        # Reserve the right-hand column for the stats grid and give the
        # icon a fixed-ish slice on the left.
        stats_w = max(180, int(w * 0.32))
        icon_size = min(int(w * 0.20), row_h)
        gutter = max(12, w // 60)
        icon_x0 = x0
        icon_x1 = icon_x0 + icon_size
        stats_x1 = x1
        stats_x0 = max(icon_x1 + gutter, stats_x1 - stats_w)

        icon_box = (
            icon_x0,
            content_top + max(0, (row_h - icon_size) // 2),
            icon_x1,
            content_top + max(0, (row_h - icon_size) // 2) + icon_size,
        )
        _draw_icon(draw, _weather_icon(cur.weather_code, cur.is_day), icon_box)

        info_x0 = icon_x1 + gutter
        info_x1 = stats_x0 - gutter // 2
        info_y = content_top + max(0, (row_h - info_h) // 2)
        draw.text((info_x0, info_y), temp_text, font=self._font_temp, fill=0)
        draw.text(
            (info_x0, info_y + th + info_gap),
            cond_text,
            font=self._font_title,
            fill=0,
        )
        draw.text(
            (info_x0, info_y + th + info_gap + ch + info_gap),
            feels_text,
            font=self._font_body,
            fill=0,
        )

        # Stats grid on the right: 2 columns × 2 rows of small label/value.
        stats: list[tuple[str, str]] = [
            ("Humidity", f"{cur.humidity}%"),
            ("Wind", f"{cur.wind_speed:.0f} {wind_unit}"),
            ("Sunrise", cur.sunrise.strftime("%H:%M") if cur.sunrise else "\u2014"),
            ("Sunset", cur.sunset.strftime("%H:%M") if cur.sunset else "\u2014"),
        ]
        stats_cols = 2
        stats_rows = 2
        cell_w = (stats_x1 - stats_x0) // stats_cols
        cell_h = row_h // stats_rows
        for idx, (label, value) in enumerate(stats):
            r, c = divmod(idx, stats_cols)
            cx0 = stats_x0 + c * cell_w
            cy0 = content_top + r * cell_h
            cxm = cx0 + cell_w // 2
            lw, lh = _text_size(draw, label, self._font_small)
            vw, vh = _text_size(draw, value, self._font_body)
            cell_gap = max(2, cell_h // 20)
            total = lh + cell_gap + vh
            content_y = cy0 + max(0, (cell_h - total) // 2)
            draw.text(
                (cxm - lw // 2, content_y), label, font=self._font_small, fill=0,
            )
            draw.text(
                (cxm - vw // 2, content_y + lh + cell_gap),
                value,
                font=self._font_body,
                fill=0,
            )

    def _draw_weather_placeholder(
        self, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        h = y1 - y0
        msg = self._weather_error or "Weather loading\u2026"
        hint = f"Town: {self._town}"
        mw, mh = _text_size(draw, msg, self._font_body)
        hw, hh = _text_size(draw, hint, self._font_small)
        gap = max(4, h // 20)
        total_h = mh + gap + hh
        y = y0 + max(0, (h - total_h) // 2)
        cx = (x0 + x1) // 2
        draw.text((cx - mw // 2, y), msg, font=self._font_body, fill=0)
        draw.text(
            (cx - hw // 2, y + mh + gap), hint, font=self._font_small, fill=0,
        )

    # ---- Quote section ----------------------------------------------- #
    def _draw_quote(
        self, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        w = x1 - x0
        h = y1 - y0

        heading = "Quote of the day"
        _, hh = _text_size(draw, heading, self._font_small)
        draw.text((x0, y0), heading, font=self._font_small, fill=0)
        text_top = y0 + hh + max(4, h // 30)

        if self._quote is None:
            msg = "Quote unavailable"
            mw, mh = _text_size(draw, msg, self._font_body)
            draw.text(
                (
                    (x0 + x1) // 2 - mw // 2,
                    text_top + max(0, (y1 - text_top - mh) // 2),
                ),
                msg,
                font=self._font_body,
                fill=0,
            )
            return

        quote_text = f"\u201c{self._quote.text}\u201d"
        author_text = f"\u2014 {self._quote.author}"
        aw, ah = _text_size(draw, author_text, self._font_quote_author)

        line_gap = max(1, h // 80)
        line_h = _text_size(draw, "Ay", self._font_quote)[1]
        available_h = max(1, y1 - text_top - ah - line_gap * 2)
        max_lines = max(1, available_h // (line_h + line_gap))

        wrapped = _wrap_text(draw, quote_text, self._font_quote, w)
        if len(wrapped) > max_lines:
            wrapped = wrapped[:max_lines]
            wrapped[-1] = _truncate_with_ellipsis(
                draw, wrapped[-1], self._font_quote, w,
            )

        total_quote_h = (
            len(wrapped) * line_h + max(0, (len(wrapped) - 1)) * line_gap
        )
        block_h = total_quote_h + line_gap * 2 + ah
        block_top = text_top + max(0, ((y1 - text_top) - block_h) // 2)

        y = block_top
        for line in wrapped:
            lw, _lh = _text_size(draw, line, self._font_quote)
            draw.text(
                ((x0 + x1) // 2 - lw // 2, y),
                line,
                font=self._font_quote,
                fill=0,
            )
            y += line_h + line_gap

        y += line_gap
        draw.text((x1 - aw, y), author_text, font=self._font_quote_author, fill=0)

    # ------------------------------------------------------------------ #
    # Data refresh                                                       #
    # ------------------------------------------------------------------ #
    def _ensure_weather(self) -> None:
        """Fetch weather at most once per hour, geocoding on first call."""
        now = datetime.now()
        if (
            self._weather is not None
            and self._weather_fetched_at is not None
            and (now - self._weather_fetched_at) < _WEATHER_MAX_AGE
        ):
            return

        if self._location is None:
            try:
                self._location = _geocode(self._town, self._country)
                _log.info(
                    "Dashboard: resolved town %r -> %s, %s (%.4f, %.4f)",
                    self._town,
                    self._location.name,
                    self._location.country,
                    self._location.latitude,
                    self._location.longitude,
                )
            except Exception as exc:
                _log.exception("Failed to geocode town %r", self._town)
                self._weather_error = f"Cannot find town '{self._town}': {exc}"
                return

        try:
            self._weather = _fetch_weather(
                self._location,
                temperature_unit=self._temp_unit,
                wind_speed_unit=self._wind_unit,
            )
            self._weather_fetched_at = now
            self._weather_error = None
        except Exception as exc:
            _log.exception("Failed to fetch weather")
            self._weather_error = f"Weather fetch failed: {exc}"

    def _ensure_quote(self) -> None:
        """Fetch the quote at most once per calendar day."""
        today = date.today()
        if self._quote is not None and self._quote.fetched_on == today:
            return

        try:
            text, author = _fetch_quote(self._quote_url)
        except Exception as exc:
            _log.warning("Failed to fetch quote of the day: %s", exc)
            if self._quote is None:
                # First-run fallback so the screen is never blank. Mark it
                # with today's date so we honour "one quote per day" even
                # when the API is unreachable — we'll retry tomorrow.
                fb_text, fb_author = _FALLBACK_QUOTE
                self._quote = Quote(
                    text=fb_text, author=fb_author, fetched_on=today,
                )
                self._save_cached_quote(self._quote)
            return

        self._quote = Quote(text=text, author=author, fetched_on=today)
        _log.info("Dashboard: new daily quote by %s", self._quote.author)
        self._save_cached_quote(self._quote)

    # ------------------------------------------------------------------ #
    # Quote cache persistence                                            #
    # ------------------------------------------------------------------ #
    def _load_cached_quote(self) -> Quote | None:
        path = self._quote_cache_path
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            _log.warning("Cannot read quote cache %s: %s", path, exc)
            return None
        try:
            payload = json.loads(raw)
            return Quote(
                text=str(payload["text"]),
                author=str(payload["author"]),
                fetched_on=date.fromisoformat(str(payload["fetched_on"])),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            _log.warning("Ignoring malformed quote cache %s: %s", path, exc)
            return None

    def _save_cached_quote(self, quote: Quote) -> None:
        path = self._quote_cache_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "text": quote.text,
                        "author": quote.author,
                        "fetched_on": quote.fetched_on.isoformat(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            _log.warning("Cannot write quote cache %s: %s", path, exc)


# --------------------------------------------------------------------------- #
# Networking                                                                   #
# --------------------------------------------------------------------------- #
def _fetch_quote(url: str) -> tuple[str, str]:
    """Return ``(text, author)`` from a ZenQuotes-compatible endpoint."""
    resp = requests.get(url, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    if isinstance(payload, list) and payload:
        entry = payload[0]
    elif isinstance(payload, dict):
        entry = payload
    else:
        raise ValueError(
            f"Unexpected quote payload shape: {type(payload).__name__}",
        )

    text = str(entry.get("q") or entry.get("content") or "").strip()
    author = str(entry.get("a") or entry.get("author") or "Unknown").strip()
    if not text:
        raise ValueError("Quote payload missing text")
    return text, author or "Unknown"


# --------------------------------------------------------------------------- #
# Text helpers                                                                 #
# --------------------------------------------------------------------------- #
def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Word-wrap ``text`` so each line fits within ``max_width`` pixels."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        cw, _ = _text_size(draw, candidate, font)
        if cw <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _truncate_with_ellipsis(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    """Return ``text`` shortened so ``text + ellipsis`` fits ``max_width``."""
    ellipsis = "\u2026"
    if _text_size(draw, text, font)[0] <= max_width:
        return text
    while text and _text_size(draw, text + ellipsis, font)[0] > max_width:
        text = text[:-1].rstrip()
    return text + ellipsis

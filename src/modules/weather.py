"""Weather module: current conditions + weekly forecast for a configured town.

The town name is read from ``config["modules"]["weather"]["town"]``. The module
resolves it to coordinates via Open-Meteo's public geocoding API, then fetches
current weather, a 7-day forecast, and European AQI air-quality once per hour
(exactly at ``:00``). Icons are drawn directly with PIL primitives so nothing
extra needs to be shipped alongside the source.

Two views share the same data:

* **detail** (default): large weather icon, big temperature, feels-like,
  condition text, and a stats grid (humidity, wind, pressure, precipitation,
  UV, air quality, sunrise/sunset).
* **forecast**: minimal 7-day grid with weekday, small icon, high/low temp
  and precipitation.

The dedicated action button (button 5) toggles between the two views.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests
from PIL import Image, ImageDraw, ImageFont

from ..module import Module
from ..registry import register_module

_log = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

_HTTP_TIMEOUT = 15  # seconds

# WMO weather-code buckets we render as icons.
_ICON_CLEAR = "clear"
_ICON_PARTLY = "partly_cloudy"
_ICON_CLOUDY = "cloudy"
_ICON_FOG = "fog"
_ICON_RAIN = "rain"
_ICON_SNOW = "snow"
_ICON_THUNDER = "thunder"


# --------------------------------------------------------------------------- #
# Data containers                                                              #
# --------------------------------------------------------------------------- #
@dataclass
class Location:
    name: str
    country: str
    latitude: float
    longitude: float
    timezone: str


@dataclass
class CurrentWeather:
    temperature: float
    feels_like: float
    humidity: int
    weather_code: int
    is_day: bool
    wind_speed: float
    wind_direction: int
    pressure: float
    precipitation: float
    uv_index: float | None
    sunrise: datetime | None
    sunset: datetime | None
    air_quality_index: int | None
    pm2_5: float | None
    pm10: float | None


@dataclass
class DailyForecast:
    date: datetime
    weather_code: int
    temp_max: float
    temp_min: float
    precipitation: float


@dataclass
class WeatherData:
    location: Location
    current: CurrentWeather
    daily: list[DailyForecast]
    fetched_at: datetime
    units: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Module                                                                       #
# --------------------------------------------------------------------------- #
@register_module("weather")
class WeatherModule(Module):
    """Current weather + weekly forecast, toggled by the action button."""

    def __init__(self, config, size):
        super().__init__(config, size)

        self._town: str = str(self.config.get("town", "London")).strip() or "London"
        self._country: str | None = (
            str(self.config["country"]).strip() if self.config.get("country") else None
        )
        self._temp_unit: str = str(self.config.get("temperature_unit", "celsius")).lower()
        self._wind_unit: str = str(self.config.get("wind_speed_unit", "kmh")).lower()

        self._view_lock = threading.Lock()
        self._view: str = "detail"
        self._location: Location | None = None
        self._weather: WeatherData | None = None
        self._weather_error: str | None = None

        # Fonts scaled from panel height so the module works on other panels too.
        h = self.height
        self._font_hero = _load_font(max(140, h // 3))
        self._font_title = _load_font(max(30, h // 14))
        self._font_body = _load_font(max(22, h // 20))
        self._font_small = _load_font(max(16, h // 28))
        self._font_stat_label = _load_font(max(14, h // 32))

    # ------------------------------------------------------------------ #
    # Scheduling & buttons                                               #
    # ------------------------------------------------------------------ #
    def next_update_delay(self) -> float:
        """Wake at the top of the next hour (``xx:00:00``)."""
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0,
        )
        return max(1.0, (next_hour - now).total_seconds())

    def on_action_button(self) -> None:
        """Toggle between the detail view and the weekly forecast."""
        with self._view_lock:
            self._view = "forecast" if self._view == "detail" else "detail"
            new_view = self._view
        _log.info("Weather view -> %s", new_view)
        super().on_action_button()

    # ------------------------------------------------------------------ #
    # Rendering                                                          #
    # ------------------------------------------------------------------ #
    def render(self) -> Image.Image:
        self._ensure_data()
        with self._view_lock:
            view = self._view

        image = self.new_image()
        draw = ImageDraw.Draw(image)

        if self._weather is None:
            self._render_error(draw)
            return image

        if view == "forecast":
            self._render_forecast(draw, self._weather)
        else:
            self._render_detail(draw, self._weather)
        return image

    def _ensure_data(self) -> None:
        """Resolve the town (once) and fetch the latest weather."""
        if self._location is None:
            try:
                self._location = _geocode(self._town, self._country)
                _log.info(
                    "Weather: resolved town %r -> %s, %s (%.4f, %.4f)",
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
            self._weather_error = None
        except Exception as exc:
            _log.exception("Failed to fetch weather")
            self._weather_error = f"Weather fetch failed: {exc}"

    # ------------------------------------------------------------------ #
    # Detail view                                                        #
    # ------------------------------------------------------------------ #
    def _render_detail(self, draw: ImageDraw.ImageDraw, data: WeatherData) -> None:
        w, h = self.width, self.height
        margin = max(12, h // 40)
        header_h = self._draw_header(draw, data, margin)

        stats_h = int(h * 0.30)
        stats_top = h - stats_h
        _hline(draw, margin, stats_top - margin // 2, w - margin)

        body_top = header_h + margin // 2
        body_bottom = stats_top - margin
        body_h = max(1, body_bottom - body_top)

        icon_w = int(w * 0.42)
        icon_box = (margin, body_top, margin + icon_w, body_top + body_h)
        _draw_icon(
            draw,
            _weather_icon(data.current.weather_code, data.current.is_day),
            icon_box,
        )

        info_x0 = margin + icon_w + margin
        info_x1 = w - margin
        temp_unit = data.units.get("temperature", "°C")
        temp_text = f"{_round_temp(data.current.temperature)}{temp_unit}"
        feels_text = (
            f"Feels like {_round_temp(data.current.feels_like)}{temp_unit}"
        )
        condition_text = _weather_description(data.current.weather_code)

        tw, th = _text_size(draw, temp_text, self._font_hero)
        fw, fh = _text_size(draw, feels_text, self._font_body)
        cw, ch = _text_size(draw, condition_text, self._font_title)

        info_h = th + max(6, h // 60) + ch + max(6, h // 60) + fh
        info_y = body_top + max(0, (body_h - info_h) // 2)
        info_cx = (info_x0 + info_x1) // 2

        draw.text(
            (info_cx - tw // 2, info_y), temp_text, font=self._font_hero, fill=0,
        )
        info_y += th + max(6, h // 60)
        draw.text(
            (info_cx - cw // 2, info_y), condition_text, font=self._font_title, fill=0,
        )
        info_y += ch + max(6, h // 60)
        draw.text(
            (info_cx - fw // 2, info_y), feels_text, font=self._font_body, fill=0,
        )

        self._draw_stats_grid(
            draw, data, (margin, stats_top, w - margin, h - margin),
        )

    def _draw_header(
        self, draw: ImageDraw.ImageDraw, data: WeatherData, margin: int,
    ) -> int:
        w = self.width
        title = data.location.name
        if data.location.country:
            title = f"{title}, {data.location.country}"
        subtitle = data.fetched_at.strftime("%a %d %b · updated %H:%M")

        _, title_h = _text_size(draw, title, self._font_title)
        _, sub_h = _text_size(draw, subtitle, self._font_small)
        sub_w, _ = _text_size(draw, subtitle, self._font_small)

        draw.text((margin, margin), title, font=self._font_title, fill=0)
        draw.text(
            (w - margin - sub_w, margin + max(0, (title_h - sub_h) // 2)),
            subtitle,
            font=self._font_small,
            fill=0,
        )
        header_bottom = margin + title_h + max(4, self.height // 80)
        _hline(draw, margin, header_bottom, w - margin)
        return header_bottom

    def _draw_stats_grid(
        self,
        draw: ImageDraw.ImageDraw,
        data: WeatherData,
        box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        cur = data.current
        temp_unit = data.units.get("temperature", "°C")
        wind_unit = data.units.get("wind_speed", "km/h")

        stats: list[tuple[str, str]] = [
            ("Humidity", f"{cur.humidity}%"),
            (
                "Wind",
                f"{cur.wind_speed:.0f} {wind_unit} {_wind_direction(cur.wind_direction)}",
            ),
            (
                "Air quality",
                _format_air_quality(cur.air_quality_index, cur.pm2_5),
            ),
            ("Pressure", f"{cur.pressure:.0f} hPa"),
            ("Precip.", f"{cur.precipitation:.1f} mm"),
            (
                "UV index",
                f"{cur.uv_index:.0f}" if cur.uv_index is not None else "—",
            ),
            (
                "Sunrise",
                cur.sunrise.strftime("%H:%M") if cur.sunrise else "—",
            ),
            (
                "Sunset",
                cur.sunset.strftime("%H:%M") if cur.sunset else "—",
            ),
        ]

        cols = 4
        rows = math.ceil(len(stats) / cols)
        cell_w = (x1 - x0) // cols
        cell_h = (y1 - y0) // rows

        for idx, (label, value) in enumerate(stats):
            r, c = divmod(idx, cols)
            cx0 = x0 + c * cell_w
            cy0 = y0 + r * cell_h
            cx1 = cx0 + cell_w
            cy1 = cy0 + cell_h

            label_w, label_h = _text_size(draw, label, self._font_stat_label)
            value_w, value_h = _text_size(draw, value, self._font_body)
            gap = max(2, cell_h // 20)
            total_h = label_h + gap + value_h
            content_y = cy0 + max(0, (cell_h - total_h) // 2)
            center_x = cx0 + (cx1 - cx0) // 2

            draw.text(
                (center_x - label_w // 2, content_y),
                label,
                font=self._font_stat_label,
                fill=0,
            )
            draw.text(
                (center_x - value_w // 2, content_y + label_h + gap),
                value,
                font=self._font_body,
                fill=0,
            )

    # ------------------------------------------------------------------ #
    # Forecast view                                                      #
    # ------------------------------------------------------------------ #
    def _render_forecast(
        self, draw: ImageDraw.ImageDraw, data: WeatherData,
    ) -> None:
        w, h = self.width, self.height
        margin = max(12, h // 40)

        title = f"7-day forecast · {data.location.name}"
        subtitle = data.fetched_at.strftime("Updated %a %d %b %H:%M")
        _, title_h = _text_size(draw, title, self._font_title)
        _, sub_h = _text_size(draw, subtitle, self._font_small)
        sub_w, _ = _text_size(draw, subtitle, self._font_small)

        draw.text((margin, margin), title, font=self._font_title, fill=0)
        draw.text(
            (w - margin - sub_w, margin + max(0, (title_h - sub_h) // 2)),
            subtitle,
            font=self._font_small,
            fill=0,
        )
        header_bottom = margin + title_h + max(4, h // 80)
        _hline(draw, margin, header_bottom, w - margin)

        days = data.daily[:7]
        if not days:
            msg = "Forecast unavailable"
            mw, mh = _text_size(draw, msg, self._font_body)
            draw.text(
                ((w - mw) // 2, (h - mh) // 2),
                msg,
                font=self._font_body,
                fill=0,
            )
            return

        cols = len(days)
        area_top = header_bottom + margin
        area_bottom = h - margin
        area_left = margin
        area_right = w - margin
        col_w = (area_right - area_left) // cols
        temp_unit = data.units.get("temperature", "°C")

        for idx, day in enumerate(days):
            cx0 = area_left + idx * col_w
            cx1 = cx0 + col_w
            # Subtle vertical separator between columns.
            if idx > 0:
                _vline(draw, cx0, area_top + margin // 2, area_bottom - margin // 2)

            day_label = (
                "Today" if idx == 0 else day.date.strftime("%a")
            )
            date_label = day.date.strftime("%d %b")
            temp_max_txt = f"{_round_temp(day.temp_max)}{temp_unit}"
            temp_min_txt = f"{_round_temp(day.temp_min)}{temp_unit}"
            precip_txt = f"{day.precipitation:.1f} mm"

            # Vertical stack: weekday / date / icon / high / low / precip
            dw, dh = _text_size(draw, day_label, self._font_body)
            date_w, date_h = _text_size(draw, date_label, self._font_small)
            hw, hh = _text_size(draw, temp_max_txt, self._font_body)
            lw, lh = _text_size(draw, temp_min_txt, self._font_small)
            pw, ph = _text_size(draw, precip_txt, self._font_stat_label)

            gap = max(4, h // 80)
            icon_size = max(48, col_w - 2 * margin - 4)
            icon_size = min(icon_size, (area_bottom - area_top) // 3)

            content_h = (
                dh + gap + date_h + gap + icon_size + gap + hh + gap + lh + gap + ph
            )
            content_y = area_top + max(0, ((area_bottom - area_top) - content_h) // 2)
            cxm = (cx0 + cx1) // 2

            draw.text(
                (cxm - dw // 2, content_y),
                day_label,
                font=self._font_body,
                fill=0,
            )
            content_y += dh + gap
            draw.text(
                (cxm - date_w // 2, content_y),
                date_label,
                font=self._font_small,
                fill=0,
            )
            content_y += date_h + gap

            icon_x0 = cxm - icon_size // 2
            icon_box = (icon_x0, content_y, icon_x0 + icon_size, content_y + icon_size)
            _draw_icon(draw, _weather_icon(day.weather_code, True), icon_box)
            content_y += icon_size + gap

            draw.text(
                (cxm - hw // 2, content_y),
                temp_max_txt,
                font=self._font_body,
                fill=0,
            )
            content_y += hh + gap
            draw.text(
                (cxm - lw // 2, content_y),
                temp_min_txt,
                font=self._font_small,
                fill=0,
            )
            content_y += lh + gap
            draw.text(
                (cxm - pw // 2, content_y),
                precip_txt,
                font=self._font_stat_label,
                fill=0,
            )

    # ------------------------------------------------------------------ #
    # Error screen                                                       #
    # ------------------------------------------------------------------ #
    def _render_error(self, draw: ImageDraw.ImageDraw) -> None:
        title = "Weather unavailable"
        detail = self._weather_error or "Waiting for first update…"
        hint = f"Configured town: {self._town}"

        tw, th = _text_size(draw, title, self._font_title)
        dw, dh = _text_size(draw, detail, self._font_body)
        hw, hh = _text_size(draw, hint, self._font_small)

        gap = max(8, self.height // 40)
        total_h = th + gap + dh + gap + hh
        y = (self.height - total_h) // 2

        draw.text(((self.width - tw) // 2, y), title, font=self._font_title, fill=0)
        y += th + gap
        draw.text(((self.width - dw) // 2, y), detail, font=self._font_body, fill=0)
        y += dh + gap
        draw.text(((self.width - hw) // 2, y), hint, font=self._font_small, fill=0)


# --------------------------------------------------------------------------- #
# Networking                                                                   #
# --------------------------------------------------------------------------- #
def _geocode(town: str, country: str | None = None) -> Location:
    """Resolve ``town`` to a :class:`Location` using Open-Meteo geocoding."""
    params: dict[str, Any] = {"name": town, "count": 5, "language": "en", "format": "json"}
    resp = requests.get(_GEOCODE_URL, params=params, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("results") or []
    if not results:
        raise LookupError(f"No geocoding results for {town!r}")

    if country:
        wanted = country.strip().lower()
        for candidate in results:
            code = str(candidate.get("country_code", "")).lower()
            name = str(candidate.get("country", "")).lower()
            if wanted in (code, name):
                return _location_from_geocode(candidate)

    return _location_from_geocode(results[0])


def _location_from_geocode(entry: dict[str, Any]) -> Location:
    return Location(
        name=str(entry.get("name") or "").strip() or "?",
        country=str(entry.get("country") or "").strip(),
        latitude=float(entry["latitude"]),
        longitude=float(entry["longitude"]),
        timezone=str(entry.get("timezone") or "auto"),
    )


def _fetch_weather(
    location: Location,
    *,
    temperature_unit: str = "celsius",
    wind_speed_unit: str = "kmh",
) -> WeatherData:
    """Fetch current conditions + 7-day forecast + air quality for ``location``."""
    weather_params: dict[str, Any] = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "is_day",
                "precipitation",
                "weather_code",
                "pressure_msl",
                "wind_speed_10m",
                "wind_direction_10m",
            ]
        ),
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "sunrise",
                "sunset",
                "uv_index_max",
            ]
        ),
        "timezone": "auto",
        "forecast_days": 7,
        "temperature_unit": temperature_unit,
        "wind_speed_unit": wind_speed_unit,
    }
    weather_resp = requests.get(_WEATHER_URL, params=weather_params, timeout=_HTTP_TIMEOUT)
    weather_resp.raise_for_status()
    weather_payload = weather_resp.json()

    aqi = pm2_5 = pm10 = None
    try:
        aq_resp = requests.get(
            _AIR_QUALITY_URL,
            params={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "current": "european_aqi,pm2_5,pm10",
                "timezone": "auto",
            },
            timeout=_HTTP_TIMEOUT,
        )
        aq_resp.raise_for_status()
        aq_current = aq_resp.json().get("current") or {}
        aqi_raw = aq_current.get("european_aqi")
        aqi = int(round(aqi_raw)) if aqi_raw is not None else None
        pm2_5 = _maybe_float(aq_current.get("pm2_5"))
        pm10 = _maybe_float(aq_current.get("pm10"))
    except Exception:
        _log.warning("Air-quality fetch failed; continuing without it", exc_info=True)

    return _build_weather_data(
        location, weather_payload, aqi=aqi, pm2_5=pm2_5, pm10=pm10,
    )


def _build_weather_data(
    location: Location,
    payload: dict[str, Any],
    *,
    aqi: int | None,
    pm2_5: float | None,
    pm10: float | None,
) -> WeatherData:
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    units = payload.get("current_units") or {}

    daily_forecasts: list[DailyForecast] = []
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []
    for idx, day in enumerate(dates):
        try:
            date = datetime.fromisoformat(day)
        except ValueError:
            continue
        daily_forecasts.append(
            DailyForecast(
                date=date,
                weather_code=_maybe_int(_get(codes, idx)) or 0,
                temp_max=_maybe_float(_get(tmax, idx)) or 0.0,
                temp_min=_maybe_float(_get(tmin, idx)) or 0.0,
                precipitation=_maybe_float(_get(precip, idx)) or 0.0,
            )
        )

    sunrises = daily.get("sunrise") or []
    sunsets = daily.get("sunset") or []

    current_weather = CurrentWeather(
        temperature=_maybe_float(current.get("temperature_2m")) or 0.0,
        feels_like=_maybe_float(current.get("apparent_temperature")) or 0.0,
        humidity=_maybe_int(current.get("relative_humidity_2m")) or 0,
        weather_code=_maybe_int(current.get("weather_code")) or 0,
        is_day=bool(current.get("is_day", 1)),
        wind_speed=_maybe_float(current.get("wind_speed_10m")) or 0.0,
        wind_direction=_maybe_int(current.get("wind_direction_10m")) or 0,
        pressure=_maybe_float(current.get("pressure_msl")) or 0.0,
        precipitation=_maybe_float(current.get("precipitation")) or 0.0,
        uv_index=_maybe_float(_get(daily.get("uv_index_max") or [], 0)),
        sunrise=_parse_local_iso(_get(sunrises, 0)),
        sunset=_parse_local_iso(_get(sunsets, 0)),
        air_quality_index=aqi,
        pm2_5=pm2_5,
        pm10=pm10,
    )

    unit_map = {
        "temperature": str(units.get("temperature_2m") or "°C"),
        "wind_speed": str(units.get("wind_speed_10m") or "km/h"),
        "humidity": str(units.get("relative_humidity_2m") or "%"),
        "pressure": str(units.get("pressure_msl") or "hPa"),
        "precipitation": str(units.get("precipitation") or "mm"),
    }

    return WeatherData(
        location=location,
        current=current_weather,
        daily=daily_forecasts,
        fetched_at=datetime.now(),
        units=unit_map,
    )


# --------------------------------------------------------------------------- #
# Formatting helpers                                                           #
# --------------------------------------------------------------------------- #
def _round_temp(value: float) -> int:
    return int(round(value))


def _wind_direction(degrees: int) -> str:
    if degrees is None:
        return ""
    points = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    idx = int((degrees % 360) / 45 + 0.5) % 8
    return points[idx]


def _format_air_quality(aqi: int | None, pm25: float | None) -> str:
    if aqi is None and pm25 is None:
        return "—"
    if aqi is None:
        return f"PM2.5 {pm25:.0f}"
    if aqi <= 20:
        label = "Good"
    elif aqi <= 40:
        label = "Fair"
    elif aqi <= 60:
        label = "Moderate"
    elif aqi <= 80:
        label = "Poor"
    elif aqi <= 100:
        label = "V. poor"
    else:
        label = "Extreme"
    return f"{aqi} {label}"


def _weather_description(code: int) -> str:
    mapping = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Rime fog",
        51: "Light drizzle",
        53: "Drizzle",
        55: "Heavy drizzle",
        56: "Freezing drizzle",
        57: "Freezing drizzle",
        61: "Light rain",
        63: "Rain",
        65: "Heavy rain",
        66: "Freezing rain",
        67: "Freezing rain",
        71: "Light snow",
        73: "Snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Rain showers",
        81: "Rain showers",
        82: "Violent showers",
        85: "Snow showers",
        86: "Snow showers",
        95: "Thunderstorm",
        96: "Storm w/ hail",
        99: "Storm w/ hail",
    }
    return mapping.get(int(code), "Unknown")


def _weather_icon(code: int, is_day: bool) -> str:
    code = int(code)
    if code == 0:
        return _ICON_CLEAR if is_day else "clear_night"
    if code in (1, 2):
        return _ICON_PARTLY if is_day else "partly_cloudy_night"
    if code == 3:
        return _ICON_CLOUDY
    if code in (45, 48):
        return _ICON_FOG
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return _ICON_RAIN
    if code in (71, 73, 75, 77, 85, 86):
        return _ICON_SNOW
    if code in (95, 96, 99):
        return _ICON_THUNDER
    return _ICON_CLOUDY


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get(seq: list, idx: int) -> Any:
    if 0 <= idx < len(seq):
        return seq[idx]
    return None


def _parse_local_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Drawing primitives                                                           #
# --------------------------------------------------------------------------- #
def _hline(draw: ImageDraw.ImageDraw, x0: int, y: int, x1: int) -> None:
    draw.line([(x0, y), (x1, y)], fill=0, width=1)


def _vline(draw: ImageDraw.ImageDraw, x: int, y0: int, y1: int) -> None:
    draw.line([(x, y0), (x, y1)], fill=0, width=1)


def _text_size(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont,
) -> tuple[int, int]:
    _, _, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right, bottom


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


# --------------------------------------------------------------------------- #
# Icons                                                                        #
# --------------------------------------------------------------------------- #
def _draw_icon(draw: ImageDraw.ImageDraw, name: str, box: tuple[int, int, int, int]) -> None:
    renderer: Callable[[ImageDraw.ImageDraw, tuple[int, int, int, int]], None] = (
        _ICON_RENDERERS.get(name) or _draw_cloud
    )
    renderer(draw, box)


def _shrink(box: tuple[int, int, int, int], padding: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return x0 + padding, y0 + padding, x1 - padding, y1 - padding


def _draw_sun(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    r_outer = min(x1 - x0, y1 - y0) // 2
    body_r = max(6, int(r_outer * 0.55))
    ray_inner = body_r + max(4, body_r // 4)
    ray_outer = int(r_outer * 0.98)
    ray_w = max(3, body_r // 6)
    for i in range(8):
        angle = i * math.pi / 4
        sx = cx + int(ray_inner * math.cos(angle))
        sy = cy + int(ray_inner * math.sin(angle))
        ex = cx + int(ray_outer * math.cos(angle))
        ey = cy + int(ray_outer * math.sin(angle))
        draw.line([(sx, sy), (ex, ey)], fill=0, width=ray_w)
    draw.ellipse(
        [cx - body_r, cy - body_r, cx + body_r, cy + body_r], fill=0,
    )


def _draw_moon(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    r = int(min(x1 - x0, y1 - y0) * 0.42)
    # Full disc, then punch a smaller white disc offset to make a crescent.
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    offset = int(r * 0.55)
    inner_r = int(r * 0.9)
    draw.ellipse(
        [cx - inner_r + offset, cy - inner_r, cx + inner_r + offset, cy + inner_r],
        fill=255,
    )


def _cloud_shape(box: tuple[int, int, int, int]) -> tuple[list[tuple[int, int, int, int]], tuple[int, int, int, int]]:
    """Return the ellipses + baseline rectangle that make up a filled cloud."""
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    baseline_y = y0 + int(h * 0.85)

    left_r = int(min(w, h) * 0.20)
    right_r = int(min(w, h) * 0.22)
    top_r = int(min(w, h) * 0.28)

    left_cx = x0 + left_r + max(2, w // 40)
    left_cy = baseline_y - left_r

    right_cx = x1 - right_r - max(2, w // 40)
    right_cy = baseline_y - right_r

    top_cx = (left_cx + right_cx) // 2
    top_cy = baseline_y - top_r - int(h * 0.05)

    circles = [
        (left_cx - left_r, left_cy - left_r, left_cx + left_r, left_cy + left_r),
        (right_cx - right_r, right_cy - right_r, right_cx + right_r, right_cy + right_r),
        (top_cx - top_r, top_cy - top_r, top_cx + top_r, top_cy + top_r),
    ]
    body = (left_cx, baseline_y - left_r, right_cx, baseline_y)
    return circles, body


def _draw_cloud(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    circles, body = _cloud_shape(box)
    for circle in circles:
        draw.ellipse(circle, fill=0)
    draw.rectangle(body, fill=0)


def _draw_partly_cloudy(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    sun_size = int(min(w, h) * 0.55)
    sun_box = (x0, y0, x0 + sun_size, y0 + sun_size)
    _draw_sun(draw, sun_box)
    cloud_box = (
        x0 + int(w * 0.25),
        y0 + int(h * 0.28),
        x1,
        y1 - max(4, h // 20),
    )
    _draw_cloud(draw, cloud_box)


def _draw_partly_cloudy_night(
    draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    moon_size = int(min(w, h) * 0.55)
    moon_box = (x0, y0, x0 + moon_size, y0 + moon_size)
    _draw_moon(draw, moon_box)
    cloud_box = (
        x0 + int(w * 0.25),
        y0 + int(h * 0.28),
        x1,
        y1 - max(4, h // 20),
    )
    _draw_cloud(draw, cloud_box)


def _draw_rain(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    h = y1 - y0
    cloud_box = (x0, y0, x1, y0 + int(h * 0.60))
    _draw_cloud(draw, cloud_box)

    drop_area_top = y0 + int(h * 0.62)
    drop_area_bottom = y1 - max(4, h // 20)
    drop_h = drop_area_bottom - drop_area_top
    if drop_h <= 0:
        return
    drop_len = int(drop_h * 0.55)
    drop_w = max(3, drop_h // 12)
    for i, frac in enumerate((0.28, 0.5, 0.72)):
        sx = x0 + int((x1 - x0) * frac)
        offset = 0 if i % 2 == 0 else drop_h // 6
        draw.line(
            [(sx, drop_area_top + offset), (sx - drop_len // 3, drop_area_top + offset + drop_len)],
            fill=0,
            width=drop_w,
        )


def _draw_snow(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    h = y1 - y0
    cloud_box = (x0, y0, x1, y0 + int(h * 0.60))
    _draw_cloud(draw, cloud_box)

    flake_area_top = y0 + int(h * 0.68)
    flake_area_bottom = y1 - max(4, h // 20)
    flake_h = flake_area_bottom - flake_area_top
    if flake_h <= 0:
        return
    flake_r = max(4, flake_h // 8)
    stroke = max(2, flake_r // 3)
    positions = (0.28, 0.5, 0.72)
    for i, frac in enumerate(positions):
        cx = x0 + int((x1 - x0) * frac)
        cy = flake_area_top + (flake_h // 2 if i % 2 == 0 else flake_h // 2 + flake_r)
        # 6-arm asterisk: 3 lines through the centre.
        for step in range(3):
            angle = step * math.pi / 3
            dx = int(flake_r * math.cos(angle))
            dy = int(flake_r * math.sin(angle))
            draw.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=0, width=stroke)
        draw.ellipse(
            [cx - stroke, cy - stroke, cx + stroke, cy + stroke], fill=0,
        )


def _draw_thunder(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    h = y1 - y0
    cloud_box = (x0, y0, x1, y0 + int(h * 0.60))
    _draw_cloud(draw, cloud_box)

    bolt_top = y0 + int(h * 0.55)
    bolt_bottom = y1 - max(4, h // 20)
    cx = (x0 + x1) // 2
    bolt_h = bolt_bottom - bolt_top
    if bolt_h <= 0:
        return
    bw = max(6, bolt_h // 6)
    polygon = [
        (cx - bw, bolt_top),
        (cx + bw * 2, bolt_top),
        (cx, bolt_top + bolt_h // 2),
        (cx + bw * 2, bolt_top + bolt_h // 2),
        (cx - bw, bolt_bottom),
        (cx + bw // 2, bolt_top + int(bolt_h * 0.55)),
        (cx - bw // 2, bolt_top + int(bolt_h * 0.55)),
    ]
    draw.polygon(polygon, fill=0)


def _draw_fog(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    cloud_box = (x0, y0, x1, y0 + int(h * 0.55))
    _draw_cloud(draw, cloud_box)
    line_area_top = y0 + int(h * 0.62)
    line_area_bottom = y1 - max(4, h // 20)
    line_h = line_area_bottom - line_area_top
    if line_h <= 0:
        return
    stroke = max(3, line_h // 12)
    gap = line_h // 4
    y = line_area_top
    lines = (
        (x0 + int(w * 0.05), x1 - int(w * 0.10)),
        (x0 + int(w * 0.15), x1 - int(w * 0.05)),
        (x0 + int(w * 0.08), x1 - int(w * 0.20)),
    )
    for lx0, lx1 in lines:
        draw.line([(lx0, y), (lx1, y)], fill=0, width=stroke)
        y += gap


_ICON_RENDERERS: dict[str, Callable[[ImageDraw.ImageDraw, tuple[int, int, int, int]], None]] = {
    _ICON_CLEAR: _draw_sun,
    "clear_night": _draw_moon,
    _ICON_PARTLY: _draw_partly_cloudy,
    "partly_cloudy_night": _draw_partly_cloudy_night,
    _ICON_CLOUDY: _draw_cloud,
    _ICON_FOG: _draw_fog,
    _ICON_RAIN: _draw_rain,
    _ICON_SNOW: _draw_snow,
    _ICON_THUNDER: _draw_thunder,
}

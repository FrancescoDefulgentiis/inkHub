"""Formula 1 module: last-race detail + season championship overview.

Data is pulled once per hour from the free `jolpica-f1
<https://api.jolpi.ca/>`_ API, a drop-in replacement for the retired Ergast
Motor Racing API that keeps the same JSON schema.

Two views share the same data set:

* **weekend** (default): header with round + circuit, a podium visualisation
  with 1st/2nd/3rd, race stats (pole, fastest lap, laps) and the full
  classification table.
* **championship**: two-column layout with the driver standings on the left
  and the constructor standings on the right.

The dedicated action button (button 5) toggles between the two views.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

import requests
from PIL import Image, ImageDraw, ImageFont

from ...module import Module
from ...registry import register_module

_log = logging.getLogger(__name__)

_BASE_URL = "https://api.jolpi.ca/ergast/f1"
_LAST_RACE_URL = f"{_BASE_URL}/current/last/results.json"
_DRIVER_STANDINGS_URL = f"{_BASE_URL}/current/driverstandings.json"
_CONSTRUCTOR_STANDINGS_URL = f"{_BASE_URL}/current/constructorstandings.json"

_HTTP_TIMEOUT = 15  # seconds

# Short 3-letter tags for teams so the classification table stays compact.
_TEAM_ABBREVIATIONS: dict[str, str] = {
    "Red Bull": "RBR",
    "Mercedes": "MER",
    "Ferrari": "FER",
    "McLaren": "MCL",
    "Aston Martin": "AST",
    "Alpine F1 Team": "ALP",
    "Williams": "WIL",
    "RB F1 Team": "RB",
    "AlphaTauri": "AT",
    "Haas F1 Team": "HAA",
    "Alfa Romeo": "ARO",
    "Sauber": "SAU",
    "Audi": "AUD",
}


# --------------------------------------------------------------------------- #
# Data containers                                                              #
# --------------------------------------------------------------------------- #
@dataclass
class RaceInfo:
    season: str
    round: str
    name: str
    circuit: str
    locality: str
    country: str
    date: datetime | None


@dataclass
class DriverResult:
    position: int
    driver_name: str
    driver_code: str
    constructor: str
    grid: int
    laps: int
    status: str
    time_text: str  # human-friendly gap or finishing time
    points: float
    fastest_lap_time: str | None
    fastest_lap_rank: int | None


@dataclass
class RaceData:
    info: RaceInfo
    results: list[DriverResult]
    fastest_lap: DriverResult | None
    pole: DriverResult | None
    fetched_at: datetime


@dataclass
class DriverStanding:
    position: int
    driver_name: str
    driver_code: str
    constructor: str
    points: float
    wins: int


@dataclass
class ConstructorStanding:
    position: int
    constructor: str
    points: float
    wins: int


@dataclass
class ChampionshipData:
    season: str
    round: str
    drivers: list[DriverStanding]
    constructors: list[ConstructorStanding]
    fetched_at: datetime = field(default_factory=datetime.now)


# --------------------------------------------------------------------------- #
# Module                                                                       #
# --------------------------------------------------------------------------- #
@register_module("formula1")
class Formula1Module(Module):
    """Last race detail + championship standings, toggled by the action button."""

    def __init__(self, config, size):
        super().__init__(config, size)

        default_view = str(self.config.get("view", "weekend")).lower()
        self._view: str = "championship" if default_view == "championship" else "weekend"
        self._view_lock = threading.Lock()

        self._race: RaceData | None = None
        self._championship: ChampionshipData | None = None
        self._error: str | None = None

        h = self.height
        self._font_title = _load_font(max(30, h // 14), bold=True)
        self._font_subtitle = _load_font(max(18, h // 24))
        self._font_body = _load_font(max(18, h // 24))
        self._font_body_bold = _load_font(max(18, h // 24), bold=True)
        self._font_small = _load_font(max(14, h // 32))
        self._font_hero = _load_font(max(60, h // 6), bold=True)
        self._font_podium_pos = _load_font(max(40, h // 9), bold=True)
        self._font_podium_name = _load_font(max(18, h // 22), bold=True)
        self._font_podium_team = _load_font(max(14, h // 30))

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
        """Toggle between the last-weekend detail and the championship overview."""
        with self._view_lock:
            self._view = "championship" if self._view == "weekend" else "weekend"
            new_view = self._view
        _log.info("Formula 1 view -> %s", new_view)
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

        if view == "championship":
            if self._championship is None:
                self._render_error(draw, "Championship unavailable")
                return image
            self._render_championship(draw, self._championship)
        else:
            if self._race is None:
                self._render_error(draw, "Last race unavailable")
                return image
            self._render_weekend(draw, self._race)
        return image

    def _ensure_data(self) -> None:
        """Refresh both data sets. Errors are stored and rendered separately."""
        try:
            self._race = _fetch_last_race()
        except Exception as exc:
            _log.exception("Failed to fetch last race")
            self._error = f"Race fetch failed: {exc}"

        try:
            self._championship = _fetch_championship()
        except Exception as exc:
            _log.exception("Failed to fetch championship standings")
            self._error = f"Standings fetch failed: {exc}"

    # ------------------------------------------------------------------ #
    # Last-weekend view                                                  #
    # ------------------------------------------------------------------ #
    def _render_weekend(self, draw: ImageDraw.ImageDraw, data: RaceData) -> None:
        w, h = self.width, self.height
        margin = max(12, h // 40)

        header_bottom = self._draw_weekend_header(draw, data, margin)

        # Split the remaining area into podium (top) + classification (bottom).
        area_top = header_bottom + margin
        area_bottom = h - margin
        area_height = area_bottom - area_top

        podium_h = int(area_height * 0.48)
        podium_bottom = area_top + podium_h

        podium_box = (margin, area_top, w - margin, podium_bottom)
        self._draw_podium(draw, data, podium_box)

        _hline(draw, margin, podium_bottom + margin // 2, w - margin)

        table_box = (margin, podium_bottom + margin, w - margin, area_bottom)
        self._draw_results_table(draw, data, table_box)

    def _draw_weekend_header(
        self, draw: ImageDraw.ImageDraw, data: RaceData, margin: int,
    ) -> int:
        w = self.width
        info = data.info

        title = f"Round {info.round} · {info.name}"
        location_parts = [p for p in (info.circuit, info.country) if p]
        subtitle_left = " · ".join(location_parts) if location_parts else "Formula 1"

        date_text = info.date.strftime("%a %d %b %Y") if info.date else ""
        updated_text = f"updated {data.fetched_at.strftime('%H:%M')}"

        _, title_h = _text_size(draw, title, self._font_title)
        date_w, date_h = _text_size(draw, date_text, self._font_subtitle)
        upd_w, upd_h = _text_size(draw, updated_text, self._font_small)

        draw.text((margin, margin), title, font=self._font_title, fill=0)
        if date_text:
            draw.text(
                (w - margin - date_w, margin + max(0, (title_h - date_h) // 2)),
                date_text,
                font=self._font_subtitle,
                fill=0,
            )

        sub_y = margin + title_h + max(2, self.height // 120)
        draw.text((margin, sub_y), subtitle_left, font=self._font_subtitle, fill=0)
        draw.text(
            (w - margin - upd_w, sub_y + max(0, (date_h - upd_h) // 2)),
            updated_text,
            font=self._font_small,
            fill=0,
        )

        _, sub_h = _text_size(draw, subtitle_left, self._font_subtitle)
        header_bottom = sub_y + max(sub_h, upd_h) + max(4, self.height // 80)
        _hline(draw, margin, header_bottom, w - margin)
        return header_bottom

    def _draw_podium(
        self,
        draw: ImageDraw.ImageDraw,
        data: RaceData,
        box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        podium_w = x1 - x0
        podium_h = y1 - y0

        # Left side: three podium blocks (2 - 1 - 3 layout).
        blocks_area_w = int(podium_w * 0.55)
        blocks_area = (x0, y0, x0 + blocks_area_w, y1)
        self._draw_podium_blocks(draw, data.results[:3], blocks_area)

        # Right side: race stats.
        stats_area = (x0 + blocks_area_w + max(8, podium_w // 40), y0, x1, y1)
        self._draw_race_stats(draw, data, stats_area)

    def _draw_podium_blocks(
        self,
        draw: ImageDraw.ImageDraw,
        top3: list[DriverResult],
        box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        area_w = x1 - x0
        area_h = y1 - y0

        if not top3:
            msg = "No results yet"
            mw, mh = _text_size(draw, msg, self._font_body)
            draw.text(
                (x0 + (area_w - mw) // 2, y0 + (area_h - mh) // 2),
                msg,
                font=self._font_body,
                fill=0,
            )
            return

        # 2nd - 1st - 3rd layout, heights proportional to finishing position.
        # If fewer than 3 finishers are known, only draw what's there.
        pos_map = {r.position: r for r in top3}
        order = [2, 1, 3]
        heights_ratio = {1: 1.00, 2: 0.78, 3: 0.62}
        gap = max(6, area_w // 40)
        block_w = max(20, (area_w - 2 * gap) // 3)

        for slot, pos in enumerate(order):
            result = pos_map.get(pos)
            if result is None:
                continue
            bx0 = x0 + slot * (block_w + gap)
            bx1 = bx0 + block_w
            bh = int(area_h * heights_ratio[pos] * 0.72)
            bh = max(bh, self._font_podium_pos.size + 8)
            by1 = y1
            by0 = by1 - bh

            # Filled block with a small white inner border to look like a rostrum.
            draw.rectangle([bx0, by0, bx1, by1], fill=0)
            border = max(2, block_w // 30)
            draw.rectangle(
                [bx0 + border, by0 + border, bx1 - border, by1 - border],
                outline=255,
                width=1,
            )

            # Big position number inside the block.
            pos_text = str(pos)
            pw, ph = _text_size(draw, pos_text, self._font_podium_pos)
            draw.text(
                (bx0 + (block_w - pw) // 2, by0 + (bh - ph) // 2),
                pos_text,
                font=self._font_podium_pos,
                fill=255,
            )

            # Driver family name + team code above the block.
            name_text = result.driver_name
            team_text = _team_short(result.constructor)
            nw, nh = _text_size(draw, name_text, self._font_podium_name)
            tw, th = _text_size(draw, team_text, self._font_podium_team)
            small_gap = max(2, area_h // 60)
            total_h = nh + small_gap + th
            label_y = max(y0, by0 - total_h - max(4, area_h // 40))

            draw.text(
                (bx0 + (block_w - nw) // 2, label_y),
                name_text,
                font=self._font_podium_name,
                fill=0,
            )
            draw.text(
                (bx0 + (block_w - tw) // 2, label_y + nh + small_gap),
                team_text,
                font=self._font_podium_team,
                fill=0,
            )

    def _draw_race_stats(
        self,
        draw: ImageDraw.ImageDraw,
        data: RaceData,
        box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        area_h = y1 - y0

        winner = data.results[0] if data.results else None
        winner_time = winner.time_text if winner else "—"
        pole_text = (
            f"{data.pole.driver_name} ({_team_short(data.pole.constructor)})"
            if data.pole
            else "—"
        )
        fastest_text = "—"
        if data.fastest_lap and data.fastest_lap.fastest_lap_time:
            fastest_text = (
                f"{data.fastest_lap.driver_name} · {data.fastest_lap.fastest_lap_time}"
            )
        laps_text = str(winner.laps) if winner and winner.laps else "—"

        stats: list[tuple[str, str]] = [
            ("Winning time", winner_time),
            ("Pole", pole_text),
            ("Fastest lap", fastest_text),
            ("Laps", laps_text),
        ]

        # Split the box vertically into N equal cells so every stat fits.
        n = len(stats)
        row_h = max(1, area_h // n)
        _, label_h = _text_size(draw, "Ag", self._font_small)
        _, value_h = _text_size(draw, "Ag", self._font_body_bold)
        gap = max(1, (row_h - label_h - value_h) // 3)

        max_width = x1 - x0
        for i, (label, value) in enumerate(stats):
            cy = y0 + i * row_h
            draw.text((x0, cy), label, font=self._font_small, fill=0)
            fitted = _fit_text(draw, value, self._font_body_bold, max_width)
            draw.text(
                (x0, cy + label_h + gap),
                fitted,
                font=self._font_body_bold,
                fill=0,
            )

    def _draw_results_table(
        self,
        draw: ImageDraw.ImageDraw,
        data: RaceData,
        box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        w = x1 - x0
        h = y1 - y0

        results = data.results
        if not results:
            msg = "No classification available"
            mw, mh = _text_size(draw, msg, self._font_body)
            draw.text(
                (x0 + (w - mw) // 2, y0 + (h - mh) // 2),
                msg,
                font=self._font_body,
                fill=0,
            )
            return

        # Column widths as fractions of available width.
        col_frac = {"pos": 0.06, "driver": 0.32, "team": 0.10, "time": 0.42, "pts": 0.10}
        cols = ["pos", "driver", "team", "time", "pts"]
        col_x: dict[str, int] = {}
        cursor = x0
        for name in cols:
            col_x[name] = cursor
            cursor += int(w * col_frac[name])
        col_end = x0 + w

        header_font = self._font_small
        row_font = self._font_body
        _, header_h = _text_size(draw, "Ag", header_font)
        _, row_h_px = _text_size(draw, "Ag", row_font)
        row_h_px = row_h_px + max(2, self.height // 200)

        # Header row.
        headers = {"pos": "Pos", "driver": "Driver", "team": "Team",
                   "time": "Time / Gap", "pts": "Pts"}
        for name in cols:
            draw.text((col_x[name], y0), headers[name], font=header_font, fill=0)
        header_bottom = y0 + header_h + max(2, h // 60)
        _hline(draw, x0, header_bottom, col_end)

        # Row area.
        rows_top = header_bottom + max(2, h // 60)
        available_rows_h = y1 - rows_top
        max_rows = max(1, available_rows_h // row_h_px)
        visible = results[:max_rows]

        for idx, r in enumerate(visible):
            ry = rows_top + idx * row_h_px
            values = {
                "pos": str(r.position),
                "driver": _fit_text(draw, r.driver_name, row_font,
                                    col_x["team"] - col_x["driver"] - 6),
                "team": _team_short(r.constructor),
                "time": _fit_text(draw, r.time_text or r.status, row_font,
                                  col_x["pts"] - col_x["time"] - 6),
                "pts": _format_points(r.points),
            }
            for name in cols:
                draw.text((col_x[name], ry), values[name], font=row_font, fill=0)

    # ------------------------------------------------------------------ #
    # Championship view                                                  #
    # ------------------------------------------------------------------ #
    def _render_championship(
        self, draw: ImageDraw.ImageDraw, data: ChampionshipData,
    ) -> None:
        w, h = self.width, self.height
        margin = max(12, h // 40)

        header_bottom = self._draw_championship_header(draw, data, margin)

        area_top = header_bottom + margin
        area_bottom = h - margin
        divider_x = w // 2

        left_box = (margin, area_top, divider_x - margin // 2, area_bottom)
        right_box = (divider_x + margin // 2, area_top, w - margin, area_bottom)

        _vline(draw, divider_x, area_top, area_bottom)

        self._draw_driver_standings(draw, data.drivers, left_box)
        self._draw_constructor_standings(draw, data.constructors, right_box)

    def _draw_championship_header(
        self, draw: ImageDraw.ImageDraw, data: ChampionshipData, margin: int,
    ) -> int:
        w = self.width
        title = f"{data.season} Championship"
        subtitle = f"after round {data.round}" if data.round else "season"
        updated = f"updated {data.fetched_at.strftime('%H:%M')}"

        _, title_h = _text_size(draw, title, self._font_title)
        upd_w, upd_h = _text_size(draw, updated, self._font_small)

        draw.text((margin, margin), title, font=self._font_title, fill=0)
        draw.text(
            (w - margin - upd_w, margin + max(0, (title_h - upd_h) // 2)),
            updated,
            font=self._font_small,
            fill=0,
        )

        sub_y = margin + title_h + max(2, self.height // 120)
        draw.text((margin, sub_y), subtitle, font=self._font_subtitle, fill=0)
        _, sub_h = _text_size(draw, subtitle, self._font_subtitle)

        header_bottom = sub_y + sub_h + max(4, self.height // 80)
        _hline(draw, margin, header_bottom, w - margin)
        return header_bottom

    def _draw_driver_standings(
        self,
        draw: ImageDraw.ImageDraw,
        drivers: list[DriverStanding],
        box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        col_title = "Drivers"
        title_w, title_h = _text_size(draw, col_title, self._font_body_bold)
        draw.text((x0, y0), col_title, font=self._font_body_bold, fill=0)

        header_y = y0 + title_h + max(4, self.height // 120)
        w = x1 - x0
        col_pos = x0
        col_name = x0 + int(w * 0.10)
        col_team = x0 + int(w * 0.55)
        col_pts = x0 + int(w * 0.82)

        headers = [("Pos", col_pos), ("Driver", col_name),
                   ("Team", col_team), ("Pts", col_pts)]
        for text, cx in headers:
            draw.text((cx, header_y), text, font=self._font_small, fill=0)
        _, hh = _text_size(draw, "Ag", self._font_small)
        _hline(draw, x0, header_y + hh + max(2, self.height // 120), x1)

        rows_top = header_y + hh + max(6, self.height // 80)
        _, row_h_px = _text_size(draw, "Ag", self._font_body)
        row_h_px += max(2, self.height // 200)
        max_rows = max(1, (y1 - rows_top) // row_h_px)
        visible = drivers[:max_rows]

        for i, d in enumerate(visible):
            ry = rows_top + i * row_h_px
            draw.text((col_pos, ry), str(d.position), font=self._font_body, fill=0)
            name_max = col_team - col_name - 6
            team_max = col_pts - col_team - 6
            draw.text(
                (col_name, ry),
                _fit_text(draw, d.driver_name, self._font_body, name_max),
                font=self._font_body,
                fill=0,
            )
            draw.text(
                (col_team, ry),
                _fit_text(draw, _team_short(d.constructor), self._font_body, team_max),
                font=self._font_body,
                fill=0,
            )
            draw.text(
                (col_pts, ry),
                _format_points(d.points),
                font=self._font_body_bold,
                fill=0,
            )

    def _draw_constructor_standings(
        self,
        draw: ImageDraw.ImageDraw,
        constructors: list[ConstructorStanding],
        box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        col_title = "Constructors"
        _, title_h = _text_size(draw, col_title, self._font_body_bold)
        draw.text((x0, y0), col_title, font=self._font_body_bold, fill=0)

        header_y = y0 + title_h + max(4, self.height // 120)
        w = x1 - x0
        col_pos = x0
        col_team = x0 + int(w * 0.12)
        col_wins = x0 + int(w * 0.64)
        col_pts = x0 + int(w * 0.82)

        headers = [("Pos", col_pos), ("Team", col_team),
                   ("Wins", col_wins), ("Pts", col_pts)]
        for text, cx in headers:
            draw.text((cx, header_y), text, font=self._font_small, fill=0)
        _, hh = _text_size(draw, "Ag", self._font_small)
        _hline(draw, x0, header_y + hh + max(2, self.height // 120), x1)

        rows_top = header_y + hh + max(6, self.height // 80)
        _, row_h_px = _text_size(draw, "Ag", self._font_body)
        row_h_px += max(2, self.height // 200)
        max_rows = max(1, (y1 - rows_top) // row_h_px)
        visible = constructors[:max_rows]

        for i, c in enumerate(visible):
            ry = rows_top + i * row_h_px
            draw.text((col_pos, ry), str(c.position), font=self._font_body, fill=0)
            team_max = col_wins - col_team - 6
            draw.text(
                (col_team, ry),
                _fit_text(draw, c.constructor, self._font_body, team_max),
                font=self._font_body,
                fill=0,
            )
            draw.text(
                (col_wins, ry),
                str(c.wins),
                font=self._font_body,
                fill=0,
            )
            draw.text(
                (col_pts, ry),
                _format_points(c.points),
                font=self._font_body_bold,
                fill=0,
            )

    # ------------------------------------------------------------------ #
    # Error screen                                                       #
    # ------------------------------------------------------------------ #
    def _render_error(self, draw: ImageDraw.ImageDraw, title: str) -> None:
        detail = self._error or "Waiting for first update…"
        hint = "Formula 1 module · " + datetime.now().strftime("%H:%M")

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
def _fetch_last_race() -> RaceData:
    resp = requests.get(_LAST_RACE_URL, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    races = ((payload.get("MRData") or {}).get("RaceTable") or {}).get("Races") or []
    if not races:
        raise LookupError("Ergast returned no races for 'current/last'")
    race = races[0]

    circuit = race.get("Circuit") or {}
    location = circuit.get("Location") or {}
    info = RaceInfo(
        season=str(race.get("season", "")),
        round=str(race.get("round", "")),
        name=str(race.get("raceName") or "Grand Prix"),
        circuit=str(circuit.get("circuitName") or ""),
        locality=str(location.get("locality") or ""),
        country=str(location.get("country") or ""),
        date=_parse_iso_date(race.get("date")),
    )

    results: list[DriverResult] = []
    for r in race.get("Results") or []:
        driver = r.get("Driver") or {}
        constructor = r.get("Constructor") or {}
        fastest = r.get("FastestLap") or {}
        fastest_time = ((fastest.get("Time") or {}).get("time")) if fastest else None

        time_field = r.get("Time") or {}
        gap_or_time = time_field.get("time") or r.get("status") or ""

        results.append(
            DriverResult(
                position=_maybe_int(r.get("position")) or 0,
                driver_name=_driver_display_name(driver),
                driver_code=str(driver.get("code") or "").strip()
                or _last_name(driver)[:3].upper(),
                constructor=str(constructor.get("name") or ""),
                grid=_maybe_int(r.get("grid")) or 0,
                laps=_maybe_int(r.get("laps")) or 0,
                status=str(r.get("status") or ""),
                time_text=str(gap_or_time),
                points=_maybe_float(r.get("points")) or 0.0,
                fastest_lap_time=str(fastest_time) if fastest_time else None,
                fastest_lap_rank=_maybe_int(fastest.get("rank")) if fastest else None,
            )
        )

    fastest_lap = next(
        (r for r in results if r.fastest_lap_rank == 1),
        None,
    )
    pole = next((r for r in results if r.grid == 1), None)

    return RaceData(
        info=info,
        results=results,
        fastest_lap=fastest_lap,
        pole=pole,
        fetched_at=datetime.now(),
    )


def _fetch_championship() -> ChampionshipData:
    driver_resp = requests.get(_DRIVER_STANDINGS_URL, timeout=_HTTP_TIMEOUT)
    driver_resp.raise_for_status()
    driver_payload = driver_resp.json()

    constructor_resp = requests.get(
        _CONSTRUCTOR_STANDINGS_URL, timeout=_HTTP_TIMEOUT,
    )
    constructor_resp.raise_for_status()
    constructor_payload = constructor_resp.json()

    d_lists = ((driver_payload.get("MRData") or {}).get("StandingsTable") or {}).get(
        "StandingsLists"
    ) or []
    c_lists = (
        (constructor_payload.get("MRData") or {}).get("StandingsTable") or {}
    ).get("StandingsLists") or []

    d_top = d_lists[0] if d_lists else {}
    c_top = c_lists[0] if c_lists else {}

    season = str(d_top.get("season") or c_top.get("season") or "")
    round_ = str(d_top.get("round") or c_top.get("round") or "")

    drivers: list[DriverStanding] = []
    for d in d_top.get("DriverStandings") or []:
        driver = d.get("Driver") or {}
        constructors = d.get("Constructors") or []
        primary_team = str(constructors[-1].get("name")) if constructors else ""
        drivers.append(
            DriverStanding(
                position=_maybe_int(d.get("position")) or 0,
                driver_name=_driver_display_name(driver),
                driver_code=str(driver.get("code") or "").strip()
                or _last_name(driver)[:3].upper(),
                constructor=primary_team,
                points=_maybe_float(d.get("points")) or 0.0,
                wins=_maybe_int(d.get("wins")) or 0,
            )
        )

    constructors: list[ConstructorStanding] = []
    for c in c_top.get("ConstructorStandings") or []:
        team = c.get("Constructor") or {}
        constructors.append(
            ConstructorStanding(
                position=_maybe_int(c.get("position")) or 0,
                constructor=str(team.get("name") or ""),
                points=_maybe_float(c.get("points")) or 0.0,
                wins=_maybe_int(c.get("wins")) or 0,
            )
        )

    return ChampionshipData(
        season=season,
        round=round_,
        drivers=drivers,
        constructors=constructors,
    )


# --------------------------------------------------------------------------- #
# Formatting helpers                                                           #
# --------------------------------------------------------------------------- #
def _driver_display_name(driver: dict[str, Any]) -> str:
    family = str(driver.get("familyName") or "").strip()
    given = str(driver.get("givenName") or "").strip()
    if family and given:
        return f"{given[:1]}. {family}"
    return family or given or str(driver.get("code") or "?")


def _last_name(driver: dict[str, Any]) -> str:
    return str(driver.get("familyName") or driver.get("givenName") or "?")


def _team_short(name: str) -> str:
    if not name:
        return "—"
    if name in _TEAM_ABBREVIATIONS:
        return _TEAM_ABBREVIATIONS[name]
    return name[:3].upper()


def _format_points(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    """Truncate ``text`` with an ellipsis so it fits inside ``max_width`` px."""
    if max_width <= 0 or not text:
        return text
    tw, _ = _text_size(draw, text, font)
    if tw <= max_width:
        return text

    ellipsis = "…"
    lo, hi = 0, len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip() + ellipsis
        cw, _ = _text_size(draw, candidate, font)
        if cw <= max_width:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best or ellipsis


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


def _parse_iso_date(value: Any) -> datetime | None:
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


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    if bold:
        candidates = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        )
    else:
        candidates = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()

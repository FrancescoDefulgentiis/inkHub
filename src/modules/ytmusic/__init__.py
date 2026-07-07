"""YouTube Music module: now-playing + up-next queue on the e-ink panel.

Two views share the same data:

* **now_playing** (default): large dithered album cover on the left,
  song title + artist(s) + album name + duration on the right.
* **queue**: the current song at the top (cover + title + artists) and
  the next few tracks stacked below with small thumbnails.

The dedicated action button (button 5) toggles between the two views.

--------------------------------------------------------------------------
Honest note on what "now playing" means here
--------------------------------------------------------------------------
YouTube Music does **not** publish a real-time playback state API. Neither
the official YouTube Data API v3 nor the community ``ytmusicapi`` library
can tell an outside app which song is playing *right now*, at what position,
or which songs the user has manually queued.

This module therefore approximates:

* "Now playing" = the most recent entry from ``YTMusic.get_history()``.
  It updates a few seconds after each song plays. For an e-ink display
  (which refreshes on the order of seconds anyway), that's a good match.
* "Up next" = ``YTMusic.get_watch_playlist(videoId=<current>)`` — YouTube
  Music's algorithmic auto-play suggestions from the current song. This is
  the same list you see in the "Up next" side panel on the web player. It
  is **not** the user's manually reordered queue.

--------------------------------------------------------------------------
Setup (one-time)
--------------------------------------------------------------------------
1. ``pip install ytmusicapi`` (already in ``requirements.txt``).
2. Produce a ``browser.json`` credentials file:

   * On any desktop, open a Chromium/Firefox browser, go to
     ``https://music.youtube.com`` and log in.
   * Open DevTools → Network tab → play a song → find any POST request to
     ``/youtubei/v1/browse`` → right-click → *Copy as cURL* (or copy the
     request headers).
   * Run ``ytmusicapi browser`` and paste the request headers when prompted.
     A ``browser.json`` file is written to the current directory.
   * Move that file into ``src/modules/ytmusic/browser.json`` (a
     ``.gitignore`` next to it prevents accidental commits).

3. Point the module at it in ``config.json`` (the default already matches
   the location above):

   .. code-block:: json

       "ytmusic": {
           "auth_file": "src/modules/ytmusic/browser.json",
           "poll_interval": 5,
           "default_view": "now_playing",
           "queue_size": 5
       }

   Relative paths are resolved from the working directory in which InkHub
   is launched (the repository root). Absolute paths are also honoured.

--------------------------------------------------------------------------
Fields the YouTube Music API exposes for each track
--------------------------------------------------------------------------
Both ``get_history()`` and ``get_watch_playlist()`` return dicts with at
least these keys (some are optional depending on the endpoint):

* ``videoId``            – YouTube video ID
* ``title``              – song title
* ``artists``            – list of ``{"name": str, "id": str}``
* ``album``              – ``{"name": str, "id": str}`` (may be missing for
  user uploads or podcast episodes)
* ``duration``           – ``"m:ss"`` string
* ``duration_seconds``   – integer
* ``thumbnails``         – list of ``{"url", "width", "height"}`` at growing
  sizes; the URL can be rewritten to request larger images (see
  ``_upscale_thumb_url``)
* ``likeStatus``         – ``"LIKE" | "DISLIKE" | "INDIFFERENT"``
* ``isExplicit``         – bool
* ``isAvailable``        – bool
* ``videoType``          – e.g. ``"MUSIC_VIDEO_TYPE_ATV"`` (audio track),
  ``"MUSIC_VIDEO_TYPE_OMV"`` (official music video)
* ``inLibrary``          – bool
* ``feedbackTokens``     – ``{"add": ..., "remove": ...}`` for library ops
* ``year``               – release year (watch-playlist entries)
* ``played``             – relative string (``"2 minutes ago"``) — history
  entries only. Not a real timestamp.
"""

from __future__ import annotations

import io
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import requests
from PIL import Image, ImageDraw, ImageFont

from ...module import Module
from ...registry import register_module

_log = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15  # seconds
_DEFAULT_POLL_INTERVAL = 5.0
_DEFAULT_QUEUE_SIZE = 5


def _ts() -> str:
    """Consistent local timestamp for module log lines."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Data containers                                                              #
# --------------------------------------------------------------------------- #
@dataclass
class Track:
    """A single YouTube Music track normalised across history/watch responses."""

    video_id: str
    title: str
    artists: str
    album: str
    duration: str
    duration_seconds: int
    thumbnail_url: str | None
    is_explicit: bool = False


@dataclass
class PlayerState:
    """Everything the render() method needs to draw a frame."""

    current: Track | None = None
    queue: list[Track] = field(default_factory=list)
    fetched_at: datetime | None = None
    error: str | None = None


# --------------------------------------------------------------------------- #
# Module                                                                       #
# --------------------------------------------------------------------------- #
@register_module("ytmusic")
class YouTubeMusicModule(Module):
    """Now-playing + up-next queue for a YouTube Music account."""

    def __init__(self, config, size):
        super().__init__(config, size)

        # --- Config -----------------------------------------------------
        self._auth_file: str = str(
            self.config.get("auth_file", "src/modules/ytmusic/browser.json")
        )
        self._poll_interval: float = float(
            self.config.get("poll_interval", _DEFAULT_POLL_INTERVAL)
        )
        self._queue_size: int = int(
            self.config.get("queue_size", _DEFAULT_QUEUE_SIZE)
        )
        self._change_confirm_polls: int = max(
            1, int(self.config.get("change_confirm_polls", 3))
        )
        default_view = str(self.config.get("default_view", "now_playing")).lower()
        self._view: str = "queue" if default_view == "queue" else "now_playing"

        # --- State ------------------------------------------------------
        self._state = PlayerState()
        self._state_lock = threading.Lock()
        self._view_lock = threading.Lock()
        self._last_pushed_key: tuple | None = None
        self._pending_track: Track | None = None
        self._pending_track_count: int = 0
        self._art_cache: dict[str, Image.Image] = {}
        self._art_cache_order: list[str] = []
        self._art_cache_limit = 16

        # --- Networking / API client ------------------------------------
        self._yt: Any = None
        self._yt_error: str | None = None

        # --- Poll thread ------------------------------------------------
        self._poll_stop = threading.Event()
        self._poll_thread: threading.Thread | None = None

        # --- Fonts (scale from panel height) ----------------------------
        h = self.height
        self._font_hero = _load_font(max(38, h // 10), bold=True)
        self._font_title = _load_font(max(26, h // 16), bold=True)
        self._font_subtitle = _load_font(max(20, h // 22))
        self._font_body = _load_font(max(18, h // 26))
        self._font_small = _load_font(max(14, h // 34))

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        super().start()
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name=f"{self.name}-poll",
        )
        self._poll_thread.start()

    def stop(self) -> None:
        self._poll_stop.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=5)
            self._poll_thread = None
        super().stop()

    def on_action_button(self) -> None:
        """Toggle between the ``now_playing`` and ``queue`` views."""
        with self._view_lock:
            self._view = "queue" if self._view == "now_playing" else "now_playing"
            new_view = self._view
        _log.info("YT Music view -> %s", new_view)
        # Force the render loop to redraw for the new view.
        with self._state_lock:
            self._last_pushed_key = None
        super().on_action_button()

    def next_update_delay(self) -> None:
        """Wait indefinitely; the poll thread wakes us when data changes."""
        return None

    # ------------------------------------------------------------------ #
    # Rendering                                                           #
    # ------------------------------------------------------------------ #
    def render(self) -> Image.Image:
        with self._state_lock:
            state = _clone_state(self._state)
        with self._view_lock:
            view = self._view

        image = self.new_image()
        draw = ImageDraw.Draw(image)

        if state.current is None:
            self._render_status(draw, state)
            return image

        if view == "queue":
            self._render_queue(draw, state)
        else:
            self._render_now_playing(draw, state)
        return image

    # ---------- Now Playing ------------------------------------------ #
    def _render_now_playing(
        self, draw: ImageDraw.ImageDraw, state: PlayerState,
    ) -> None:
        assert state.current is not None
        w, h = self.width, self.height
        margin = max(12, h // 40)

        header_bottom = self._draw_header(draw, "Now Playing", state, margin)

        body_top = header_bottom + margin
        body_bottom = h - margin
        body_h = body_bottom - body_top

        # Album cover: square, up to 50% of width, capped by body height.
        cover_side = min(int(w * 0.48), body_h)
        cover_box = (
            margin,
            body_top + (body_h - cover_side) // 2,
            margin + cover_side,
            body_top + (body_h - cover_side) // 2 + cover_side,
        )
        self._paste_cover(draw._image, state.current.thumbnail_url, cover_box)  # type: ignore[attr-defined]
        _rect_outline(draw, cover_box)

        info_x0 = cover_box[2] + margin
        info_x1 = w - margin
        info_w = max(1, info_x1 - info_x0)

        title = state.current.title
        if state.current.is_explicit:
            title = f"[E] {title}"
        artists = state.current.artists or "Unknown artist"
        album = state.current.album or ""
        duration = state.current.duration or ""

        lines: list[tuple[str, ImageFont.ImageFont, int]] = []
        # Title — auto-shrink so it fits width; wrap up to 2 lines.
        title_font, title_lines = _fit_wrapped(
            draw, title, self._font_hero, info_w, max_lines=2, min_size=24,
        )
        for line in title_lines:
            lines.append((line, title_font, max(4, h // 60)))

        artist_font, artist_lines = _fit_wrapped(
            draw, artists, self._font_title, info_w, max_lines=2, min_size=18,
        )
        for line in artist_lines:
            lines.append((line, artist_font, max(4, h // 80)))

        if album:
            album_font, album_lines = _fit_wrapped(
                draw, album, self._font_subtitle, info_w, max_lines=2, min_size=16,
            )
            for line in album_lines:
                lines.append((line, album_font, max(4, h // 100)))

        if duration:
            lines.append((f"Duration  {duration}", self._font_body, max(4, h // 80)))

        _draw_stacked_lines(
            draw,
            lines,
            (info_x0, body_top, info_x1, body_bottom),
        )

    # ---------- Queue ------------------------------------------------ #
    def _render_queue(
        self, draw: ImageDraw.ImageDraw, state: PlayerState,
    ) -> None:
        assert state.current is not None
        w, h = self.width, self.height
        margin = max(12, h // 40)

        header_bottom = self._draw_header(draw, "Up Next", state, margin)

        # Top card: current song, ~35% of remaining height.
        area_top = header_bottom + margin
        area_bottom = h - margin
        area_h = area_bottom - area_top
        top_h = int(area_h * 0.38)

        top_box = (margin, area_top, w - margin, area_top + top_h)
        self._draw_queue_current(draw, state.current, top_box)

        _hline(draw, margin, area_top + top_h + margin // 2, w - margin)

        # List of upcoming tracks below.
        list_top = area_top + top_h + margin
        list_box = (margin, list_top, w - margin, area_bottom)
        self._draw_queue_list(draw, state.queue[: self._queue_size], list_box)

    def _draw_queue_current(
        self,
        draw: ImageDraw.ImageDraw,
        track: Track,
        box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        h = y1 - y0
        cover_side = min(h, (x1 - x0) // 3)
        cover_box = (x0, y0, x0 + cover_side, y0 + cover_side)
        # Centre vertically inside the top card.
        cy_offset = max(0, (h - cover_side) // 2)
        cover_box = (
            cover_box[0],
            cover_box[1] + cy_offset,
            cover_box[2],
            cover_box[3] + cy_offset,
        )
        self._paste_cover(draw._image, track.thumbnail_url, cover_box)  # type: ignore[attr-defined]
        _rect_outline(draw, cover_box)

        text_x0 = cover_box[2] + max(12, h // 12)
        text_x1 = x1
        text_w = max(1, text_x1 - text_x0)

        title_font, title_lines = _fit_wrapped(
            draw, track.title, self._font_title, text_w, max_lines=2, min_size=20,
        )
        artist_font, artist_lines = _fit_wrapped(
            draw,
            track.artists or "Unknown artist",
            self._font_subtitle,
            text_w,
            max_lines=1,
            min_size=16,
        )

        lines: list[tuple[str, ImageFont.ImageFont, int]] = []
        for line in title_lines:
            lines.append((line, title_font, max(2, h // 40)))
        for line in artist_lines:
            lines.append((line, artist_font, max(2, h // 60)))
        if track.album:
            album_font, album_lines = _fit_wrapped(
                draw, track.album, self._font_body, text_w, max_lines=1, min_size=14,
            )
            for line in album_lines:
                lines.append((line, album_font, 0))

        _draw_stacked_lines(draw, lines, (text_x0, y0, text_x1, y1))

    def _draw_queue_list(
        self,
        draw: ImageDraw.ImageDraw,
        tracks: list[Track],
        box: tuple[int, int, int, int],
    ) -> None:
        x0, y0, x1, y1 = box
        if not tracks:
            msg = "No suggestions from YouTube Music yet."
            mw, mh = _text_size(draw, msg, self._font_body)
            draw.text(
                (x0 + ((x1 - x0) - mw) // 2, y0 + ((y1 - y0) - mh) // 2),
                msg,
                font=self._font_body,
                fill=0,
            )
            return

        rows = len(tracks)
        row_h = (y1 - y0) // rows
        if row_h <= 0:
            return
        thumb_side = min(row_h - max(4, row_h // 8), (x1 - x0) // 8)
        thumb_side = max(24, thumb_side)

        # Only stack an artist line if the row is tall enough to fit
        # a title + gap + artist. Otherwise show just the title.
        min_stacked_row = 44
        show_artist = row_h >= min_stacked_row
        show_separator = row_h >= 32

        for idx, track in enumerate(tracks):
            ry0 = y0 + idx * row_h
            ry1 = ry0 + row_h
            # Row separator (skip the first).
            if idx > 0 and show_separator:
                _hline(draw, x0, ry0, x1, dash=True)

            # Position number.
            pos_text = f"{idx + 1}."
            pw, ph = _text_size(draw, pos_text, self._font_subtitle)
            draw.text(
                (x0, ry0 + (row_h - ph) // 2),
                pos_text,
                font=self._font_subtitle,
                fill=0,
            )

            # Thumbnail.
            thumb_x0 = x0 + pw + max(6, thumb_side // 8)
            thumb_y0 = ry0 + (row_h - thumb_side) // 2
            thumb_box = (
                thumb_x0,
                thumb_y0,
                thumb_x0 + thumb_side,
                thumb_y0 + thumb_side,
            )
            self._paste_cover(draw._image, track.thumbnail_url, thumb_box)  # type: ignore[attr-defined]
            _rect_outline(draw, thumb_box)

            # Text.
            text_x0 = thumb_box[2] + max(8, thumb_side // 6)
            duration = track.duration or ""
            dw, dh = _text_size(draw, duration, self._font_small) if duration else (0, 0)
            duration_x = x1 - dw
            text_x1 = duration_x - max(8, thumb_side // 6) if duration else x1
            text_w = max(1, text_x1 - text_x0)

            title_font, title_lines = _fit_wrapped(
                draw, track.title, self._font_body, text_w, max_lines=1, min_size=14,
            )
            _, title_h = _text_size(draw, title_lines[0], title_font)

            if show_artist:
                artist_font, artist_lines = _fit_wrapped(
                    draw,
                    track.artists or "Unknown artist",
                    self._font_small,
                    text_w,
                    max_lines=1,
                    min_size=12,
                )
                gap = max(2, row_h // 20)
                _, artist_h = _text_size(draw, artist_lines[0], artist_font)
                total_h = title_h + gap + artist_h
                ty = ry0 + (row_h - total_h) // 2
                draw.text((text_x0, ty), title_lines[0], font=title_font, fill=0)
                draw.text(
                    (text_x0, ty + title_h + gap),
                    artist_lines[0],
                    font=artist_font,
                    fill=0,
                )
            else:
                # Compact single-line row: put title (larger) with artist appended
                # if there's still slack width; otherwise just the title.
                combined = track.title
                if track.artists:
                    combined = f"{track.title} — {track.artists}"
                combo_font, combo_lines = _fit_wrapped(
                    draw, combined, self._font_body, text_w, max_lines=1, min_size=12,
                )
                _, combo_h = _text_size(draw, combo_lines[0], combo_font)
                draw.text(
                    (text_x0, ry0 + (row_h - combo_h) // 2),
                    combo_lines[0],
                    font=combo_font,
                    fill=0,
                )

            if duration:
                draw.text(
                    (duration_x, ry0 + (row_h - dh) // 2),
                    duration,
                    font=self._font_small,
                    fill=0,
                )

    # ---------- Header + status --------------------------------------- #
    def _draw_header(
        self,
        draw: ImageDraw.ImageDraw,
        title: str,
        state: PlayerState,
        margin: int,
    ) -> int:
        w = self.width
        if state.fetched_at is not None:
            sub = f"Updated {state.fetched_at.strftime('%H:%M:%S')}"
        else:
            sub = "Waiting for data…"

        _, title_h = _text_size(draw, title, self._font_title)
        sub_w, sub_h = _text_size(draw, sub, self._font_small)

        draw.text((margin, margin), title, font=self._font_title, fill=0)
        draw.text(
            (w - margin - sub_w, margin + max(0, (title_h - sub_h) // 2)),
            sub,
            font=self._font_small,
            fill=0,
        )
        header_bottom = margin + title_h + max(4, self.height // 80)
        _hline(draw, margin, header_bottom, w - margin)
        return header_bottom

    def _render_status(
        self, draw: ImageDraw.ImageDraw, state: PlayerState,
    ) -> None:
        title = "YouTube Music"
        if state.error:
            detail = state.error
        elif self._yt_error:
            detail = self._yt_error
        else:
            detail = "Fetching your latest activity…"
        hint = f"Auth file: {self._auth_file}"

        w = self.width
        margin = max(12, self.height // 40)
        text_w = w - 2 * margin

        tw, th = _text_size(draw, title, self._font_title)
        detail_font, detail_lines = _fit_wrapped(
            draw, detail, self._font_body, text_w, max_lines=4, min_size=14,
        )
        hint_font, hint_lines = _fit_wrapped(
            draw, hint, self._font_small, text_w, max_lines=2, min_size=12,
        )

        gap = max(8, self.height // 40)
        _, detail_line_h = _text_size(draw, detail_lines[0], detail_font)
        _, hint_line_h = _text_size(draw, hint_lines[0], hint_font)
        detail_h = detail_line_h * len(detail_lines) + max(0, len(detail_lines) - 1) * (detail_line_h // 4)
        hint_h = hint_line_h * len(hint_lines) + max(0, len(hint_lines) - 1) * (hint_line_h // 4)
        total_h = th + gap + detail_h + gap + hint_h
        y = (self.height - total_h) // 2

        draw.text(((w - tw) // 2, y), title, font=self._font_title, fill=0)
        y += th + gap

        for line in detail_lines:
            lw, lh = _text_size(draw, line, detail_font)
            draw.text(((w - lw) // 2, y), line, font=detail_font, fill=0)
            y += lh + lh // 4
        y += gap - (detail_line_h // 4)

        for line in hint_lines:
            lw, lh = _text_size(draw, line, hint_font)
            draw.text(((w - lw) // 2, y), line, font=hint_font, fill=0)
            y += lh + lh // 4

    # ------------------------------------------------------------------ #
    # Album art helpers                                                  #
    # ------------------------------------------------------------------ #
    def _paste_cover(
        self,
        canvas: Image.Image,
        url: str | None,
        box: tuple[int, int, int, int],
    ) -> None:
        """Paste a 1-bit dithered album cover into ``box`` on the canvas."""
        x0, y0, x1, y1 = box
        w = max(1, x1 - x0)
        h = max(1, y1 - y0)
        art = self._load_cover(url, max(w, h)) if url else None
        if art is None:
            # Draw a placeholder note glyph on a filled square.
            draw = ImageDraw.Draw(canvas)
            draw.rectangle(box, fill=0)
            note = "♪"
            note_font = _load_font(max(24, min(w, h) // 2), bold=True)
            nw, nh = _text_size(draw, note, note_font)
            draw.text(
                (x0 + (w - nw) // 2, y0 + (h - nh) // 2),
                note,
                font=note_font,
                fill=255,
            )
            return
        art_resized = art.resize((w, h))
        canvas.paste(art_resized, (x0, y0))

    def _load_cover(self, url: str, target_side: int) -> Image.Image | None:
        """Fetch, upscale, resize, and dither a cover URL to 1-bit."""
        key = f"{url}@{target_side}"
        cached = self._art_cache.get(key)
        if cached is not None:
            return cached

        upscaled = _upscale_thumb_url(url, target_side)
        try:
            resp = requests.get(upscaled, timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            raw = Image.open(io.BytesIO(resp.content))
            raw.load()
        except Exception:
            _log.warning("Failed to load album art %s", upscaled, exc_info=True)
            return None
        # Convert to grayscale first so Floyd-Steinberg dithering has good input.
        gray = raw.convert("L")
        # Slight contrast boost helps 1-bit output.
        gray = _autocontrast(gray)
        # Resize with high-quality filter before dithering.
        gray = gray.resize((target_side, target_side), Image.LANCZOS)
        one_bit = gray.convert("1", dither=Image.FLOYDSTEINBERG)

        # Cache it (bounded LRU).
        self._art_cache[key] = one_bit
        self._art_cache_order.append(key)
        while len(self._art_cache_order) > self._art_cache_limit:
            old = self._art_cache_order.pop(0)
            self._art_cache.pop(old, None)
        return one_bit

    # ------------------------------------------------------------------ #
    # Data polling                                                       #
    # ------------------------------------------------------------------ #
    def _poll_loop(self) -> None:
        # Delay first request slightly so start() returns quickly.
        while not self._poll_stop.is_set():
            self._poll_once()
            self._poll_stop.wait(timeout=self._poll_interval)

    def _poll_once(self) -> None:
        client = self._ensure_client()
        if client is None:
            self._store_state(error=self._yt_error)
            return
        try:
            history = client.get_history()
        except Exception as exc:
            _log.exception("YT Music history fetch failed")
            self._store_state(error=f"History fetch failed: {exc}")
            return

        if not history:
            self._store_state(error="Your play history is empty.")
            return

        current_raw = history[0]
        current = _track_from_history_item(current_raw)
        if current is None:
            self._store_state(error="Latest history entry had no videoId.")
            return

        with self._state_lock:
            previous_current = self._state.current

        # get_history() can briefly flap between two recent tracks around
        # transitions. Only accept a change after N consecutive confirmations.
        effective_current = current
        if previous_current is not None and previous_current.video_id != current.video_id:
            if (
                self._pending_track is not None
                and self._pending_track.video_id == current.video_id
            ):
                self._pending_track_count += 1
            else:
                self._pending_track = current
                self._pending_track_count = 1

            if self._pending_track_count < self._change_confirm_polls:
                # Keep rendering the last committed track until stable.
                effective_current = previous_current
            else:
                self._pending_track = None
                self._pending_track_count = 0
        else:
            self._pending_track = None
            self._pending_track_count = 0

        # If the current video hasn't changed, keep the queue we already have —
        # this avoids extra network chatter every poll.
        with self._state_lock:
            same_current = (
                self._state.current is not None
                and self._state.current.video_id == effective_current.video_id
                and self._state.queue
            )

        queue: list[Track] = []
        if same_current:
            with self._state_lock:
                queue = list(self._state.queue)
        else:
            try:
                watch = client.get_watch_playlist(
                    videoId=effective_current.video_id, limit=self._queue_size + 3,
                )
                raw_tracks = watch.get("tracks") or []
                queue = [
                    t for t in (_track_from_watch_item(item) for item in raw_tracks[1:])
                    if t is not None
                ][: self._queue_size]
            except Exception:
                _log.warning(
                    "YT Music watch-playlist fetch failed", exc_info=True,
                )

        self._store_state(current=effective_current, queue=queue, error=None)

    def _store_state(
        self,
        *,
        current: Track | None = None,
        queue: list[Track] | None = None,
        error: str | None = None,
    ) -> None:
        """Update the render state and wake the render thread if it changed."""
        with self._state_lock:
            self._state.current = current if current is not None else self._state.current
            if queue is not None:
                self._state.queue = queue
            self._state.error = error
            self._state.fetched_at = datetime.now()

            # A cheap fingerprint of what render() would draw.
            key = (
                self._state.current.video_id if self._state.current else None,
                tuple(t.video_id for t in self._state.queue),
                error or "",
            )
            changed = key != self._last_pushed_key
            if changed:
                self._last_pushed_key = key

        if changed:
            self._render_wake.set()

    def _ensure_client(self) -> Any | None:
        """Lazy-import and instantiate the ``YTMusic`` client."""
        if self._yt is not None:
            return self._yt
        try:
            from ytmusicapi import YTMusic
        except ImportError:
            self._yt_error = (
                "ytmusicapi is not installed. Run: pip install ytmusicapi"
            )
            _log.error(self._yt_error)
            return None

        auth_path = Path(self._auth_file)
        if not auth_path.is_absolute():
            # Resolve relative to the repository root (where config.json lives).
            auth_path = Path.cwd() / auth_path
        if not auth_path.exists():
            self._yt_error = (
                f"Auth file not found: {auth_path}. "
                "Run `ytmusicapi browser` to create browser.json."
            )
            _log.error(self._yt_error)
            return None

        try:
            self._yt = YTMusic(str(auth_path))
            _log.info("YT Music client ready (auth: %s)", auth_path.name)
            self._yt_error = None
        except Exception as exc:
            self._yt_error = f"YTMusic client init failed: {exc}"
            _log.exception("YTMusic client init failed")
            self._yt = None
        return self._yt


# --------------------------------------------------------------------------- #
# API → Track conversion                                                       #
# --------------------------------------------------------------------------- #
def _track_from_history_item(item: dict[str, Any]) -> Track | None:
    video_id = item.get("videoId")
    if not video_id:
        return None
    return Track(
        video_id=str(video_id),
        title=str(item.get("title") or "Unknown title").strip(),
        artists=_join_artists(item.get("artists")),
        album=_album_name(item.get("album")),
        duration=str(item.get("duration") or "").strip(),
        duration_seconds=int(item.get("duration_seconds") or 0),
        thumbnail_url=_pick_thumbnail(item.get("thumbnails")),
        is_explicit=bool(item.get("isExplicit", False)),
    )


def _track_from_watch_item(item: dict[str, Any]) -> Track | None:
    video_id = item.get("videoId")
    if not video_id:
        return None
    # Watch playlists use "length" instead of "duration"; either "thumbnail" or
    # "thumbnails" for the image list.
    thumbs = item.get("thumbnail") or item.get("thumbnails")
    length = item.get("length") or item.get("duration") or ""
    return Track(
        video_id=str(video_id),
        title=str(item.get("title") or "Unknown title").strip(),
        artists=_join_artists(item.get("artists")),
        album=_album_name(item.get("album")),
        duration=str(length).strip(),
        duration_seconds=int(item.get("duration_seconds") or 0),
        thumbnail_url=_pick_thumbnail(thumbs),
        is_explicit=bool(item.get("isExplicit", False)),
    )


def _join_artists(artists: Any) -> str:
    if not artists:
        return ""
    if isinstance(artists, str):
        return artists
    names: list[str] = []
    for entry in artists:
        if isinstance(entry, dict):
            name = str(entry.get("name") or "").strip()
        else:
            name = str(entry).strip()
        if name:
            names.append(name)
    return ", ".join(names)


def _album_name(album: Any) -> str:
    if isinstance(album, dict):
        return str(album.get("name") or "").strip()
    if isinstance(album, str):
        return album.strip()
    return ""


def _pick_thumbnail(thumbs: Any) -> str | None:
    if not thumbs:
        return None
    if isinstance(thumbs, str):
        return thumbs
    # Take the largest by width (thumbnails come sorted small→large but be defensive).
    best: dict[str, Any] | None = None
    best_area = -1
    for entry in thumbs:
        if not isinstance(entry, dict):
            continue
        w = int(entry.get("width") or 0)
        h = int(entry.get("height") or 0)
        area = w * h
        if area > best_area:
            best_area = area
            best = entry
    if best is None:
        return None
    return str(best.get("url") or "") or None


# --------------------------------------------------------------------------- #
# Utilities                                                                    #
# --------------------------------------------------------------------------- #
_THUMB_SIZE_RE = re.compile(r"=w\d+-h\d+")


def _upscale_thumb_url(url: str, target_side: int) -> str:
    """Rewrite the Google CDN size params so a bigger image is returned."""
    side = max(64, int(target_side))
    if "=w" in url and "-h" in url:
        return _THUMB_SIZE_RE.sub(f"=w{side}-h{side}", url, count=1)
    # Some URLs use "=s<size>" instead.
    return re.sub(r"=s\d+", f"=s{side}", url, count=1) or url


def _autocontrast(image: Image.Image) -> Image.Image:
    """Cheap contrast stretch on an "L" image so dithering has more range."""
    from PIL import ImageOps

    try:
        return ImageOps.autocontrast(image, cutoff=1)
    except Exception:
        return image


def _clone_state(state: PlayerState) -> PlayerState:
    return PlayerState(
        current=state.current,
        queue=list(state.queue),
        fetched_at=state.fetched_at,
        error=state.error,
    )


# --------------------------------------------------------------------------- #
# Drawing primitives                                                           #
# --------------------------------------------------------------------------- #
def _hline(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y: int,
    x1: int,
    *,
    dash: bool = False,
) -> None:
    if not dash:
        draw.line([(x0, y), (x1, y)], fill=0, width=1)
        return
    step = 6
    for x in range(x0, x1, step * 2):
        draw.line([(x, y), (min(x + step, x1), y)], fill=0, width=1)


def _rect_outline(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    width: int = 1,
) -> None:
    draw.rectangle(box, outline=0, width=width)


def _text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> tuple[int, int]:
    if not text:
        return 0, 0
    _, _, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right, bottom


def _draw_stacked_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[tuple[str, ImageFont.ImageFont, int]],
    box: tuple[int, int, int, int],
) -> None:
    """Draw ``lines`` (text, font, gap-after) top-aligned within ``box``.

    Each entry's ``gap`` is added *after* its line. If the total height exceeds
    the box, later lines are silently dropped.
    """
    x0, y0, x1, y1 = box
    y = y0
    for text, font, gap in lines:
        if not text:
            continue
        tw, th = _text_size(draw, text, font)
        if y + th > y1:
            break
        # Truncate if a single word/glyph is somehow wider than the box.
        display = _ellipsize(draw, text, font, x1 - x0)
        draw.text((x0, y), display, font=font, fill=0)
        y += th + gap


def _ellipsize(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    """Return ``text`` shortened with an ellipsis if it doesn't fit ``max_width``."""
    if max_width <= 0:
        return text
    if _text_size(draw, text, font)[0] <= max_width:
        return text
    ellipsis = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid].rstrip() + ellipsis
        if _text_size(draw, candidate, font)[0] <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ellipsis if lo > 0 else ellipsis


def _fit_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    *,
    max_lines: int = 2,
    min_size: int = 12,
    step: int = 2,
) -> tuple[ImageFont.ImageFont, list[str]]:
    """Shrink the font until ``text`` wraps into ≤ ``max_lines`` lines.

    Returns the chosen font and the wrapped lines. If even at ``min_size`` the
    text won't fit, the last line is ellipsised.
    """
    if not text:
        return font, [""]
    current_font = font
    current_size = _font_size(current_font)
    while True:
        lines = _wrap_text(draw, text, current_font, max_width, max_lines)
        if len(lines) <= max_lines:
            return current_font, lines
        new_size = current_size - step
        if new_size < min_size:
            # Give up: ellipsise the last allowed line.
            lines = _wrap_text(
                draw, text, current_font, max_width, max_lines, force_ellipsize=True,
            )
            return current_font, lines
        current_font = _load_font(new_size, bold=_font_is_bold(current_font))
        current_size = new_size


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
    *,
    force_ellipsize: bool = False,
) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_size(draw, candidate, font)[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
                current = word
            else:
                # Single word wider than the box: split by ellipsize.
                lines.append(_ellipsize(draw, word, font, max_width))
                current = ""
            if force_ellipsize and len(lines) >= max_lines:
                break
    if current:
        lines.append(current)

    if len(lines) > max_lines:
        if force_ellipsize:
            keep = lines[:max_lines]
            keep[-1] = _ellipsize(
                draw, " ".join(lines[max_lines - 1 :]), font, max_width,
            )
            return keep
        # Return the overflowing list so the caller knows to shrink the font.
        return lines
    return lines


# --------------------------------------------------------------------------- #
# Fonts                                                                        #
# --------------------------------------------------------------------------- #
_FONT_PATHS_REGULAR = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
)
_FONT_PATHS_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    paths: Iterable[str] = _FONT_PATHS_BOLD if bold else _FONT_PATHS_REGULAR
    for path in paths:
        try:
            font = ImageFont.truetype(path, size)
            # Tag the font instance so _fit_wrapped can rebuild at a new size.
            font.__inkhub_bold__ = bold  # type: ignore[attr-defined]
            font.__inkhub_size__ = size  # type: ignore[attr-defined]
            return font
        except OSError:
            continue
    _log.warning("No TrueType font found; falling back to Pillow default")
    default = ImageFont.load_default()
    default.__inkhub_bold__ = bold  # type: ignore[attr-defined]
    default.__inkhub_size__ = size  # type: ignore[attr-defined]
    return default


def _font_size(font: ImageFont.ImageFont) -> int:
    size = getattr(font, "__inkhub_size__", None)
    if size is not None:
        return int(size)
    size = getattr(font, "size", None)
    return int(size) if size else 16


def _font_is_bold(font: ImageFont.ImageFont) -> bool:
    return bool(getattr(font, "__inkhub_bold__", False))

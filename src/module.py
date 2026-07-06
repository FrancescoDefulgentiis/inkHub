"""Service Blueprint — the abstract contract every InkHub module must satisfy."""

from __future__ import annotations

import logging
import queue as _queue
import threading
from abc import ABC, abstractmethod
from typing import Any, Mapping

from PIL import Image

_log = logging.getLogger(__name__)


class Module(ABC):
    """Abstract base class for every InkHub module.

    A module is a small, self-contained "screen" that knows how to draw
    itself onto a Pillow image sized to the e-ink panel. It may optionally
    react to the dedicated action button or schedule its own future redraws.

    Rendered images are placed into a single-slot :attr:`image_queue`. The
    app consumes from that queue; if it is empty the display is left unchanged.
    """

    #: Human-readable name, set automatically by :func:`register_module`.
    name: str = ""

    def __init__(self, config: Mapping[str, Any], size: tuple[int, int]) -> None:
        """Initialise the module.

        :param config: The module-specific configuration block from
            ``config.json`` (i.e. ``config["modules"][<name>]``). May be empty.
        :param size: ``(width, height)`` of the target e-ink panel in pixels.
        """
        self.config: Mapping[str, Any] = config or {}
        self.width, self.height = size
        self._image_queue: _queue.Queue[Image.Image] = _queue.Queue(maxsize=1)
        self._render_stop = threading.Event()
        self._render_wake = threading.Event()
        self._render_thread: threading.Thread | None = None

    @property
    def image_queue(self) -> _queue.Queue[Image.Image]:
        """Single-slot buffer: the most recently rendered image, if any."""
        return self._image_queue

    # ------------------------------------------------------------------ #
    # Lifecycle hooks — override as needed.                              #
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Called once, right after the module is instantiated.

        The default implementation launches a background render thread that
        calls :meth:`render` repeatedly on the schedule returned by
        :meth:`next_update_delay` and pushes each result into :attr:`image_queue`.
        """
        self._render_stop.clear()
        self._render_thread = threading.Thread(
            target=self._render_loop,
            daemon=True,
            name=f"{self.name}-render",
        )
        self._render_thread.start()

    def stop(self) -> None:
        """Called once, when the app is shutting down."""
        self._render_stop.set()
        self._render_wake.set()
        if self._render_thread is not None:
            self._render_thread.join(timeout=5)
            self._render_thread = None

    def on_action_button(self) -> None:
        """Handle the dedicated module action button.

        The default implementation wakes the render thread so a fresh image
        is produced immediately. Override to add custom behaviour, calling
        ``super().on_action_button()`` to preserve the wake-up.
        """
        self._render_wake.set()

    def next_update_delay(self) -> float | None:
        """Return seconds until the next display refresh, or ``None``.

        Returning ``None`` tells the render thread to wait until an external
        event (e.g. the action button) calls :meth:`on_action_button`.
        """
        return None

    def new_image(self, color: int = 255) -> Image.Image:
        """Create a new 1-bit image for the module to render."""
        return Image.new("1", (self.width, self.height), color)

    # ------------------------------------------------------------------ #
    # Internal render loop                                               #
    # ------------------------------------------------------------------ #
    def _push_image(self, image: Image.Image) -> None:
        """Replace any pending image in the queue with *image*."""
        try:
            self._image_queue.get_nowait()
        except _queue.Empty:
            pass
        self._image_queue.put(image)

    def _render_loop(self) -> None:
        """Background thread: render → push → wait → repeat."""
        while not self._render_stop.is_set():
            try:
                image = self.render()
                self._push_image(image)
            except Exception:
                _log.exception("Module %r render() raised", self.name)

            delay = self.next_update_delay()
            if delay is None:
                self._render_wake.wait()
                self._render_wake.clear()
            elif delay > 0:
                self._render_wake.wait(timeout=delay)
                self._render_wake.clear()
            # delay == 0: re-render immediately without waiting

    # ------------------------------------------------------------------ #
    # Required rendering hook.                                           #
    # ------------------------------------------------------------------ #
    @abstractmethod
    def render(self) -> Image.Image:
        """Return the next image to push to the e-ink display."""

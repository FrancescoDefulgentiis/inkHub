"""Service Blueprint — the abstract contract every InkHub module must satisfy.

To add a new module:
    1. Create ``inkhub/modules/<name>.py``.
    2. Subclass :class:`Module` and implement :meth:`render`.
    3. Decorate the class with ``@register_module("<name>")``.
    4. Set ``active_module`` to ``"<name>"`` in ``config.json``.

The rest of InkHub (display, buttons, main loop) will pick it up automatically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from PIL import Image, ImageDraw


class Module(ABC):
    """Abstract base class for every InkHub module.

    A module is a small, self-contained "screen" that knows how to draw
    itself onto a Pillow image sized to the e-ink panel. It may optionally
    react to button presses.
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

    # ------------------------------------------------------------------ #
    # Lifecycle hooks — override as needed. Defaults are no-ops.         #
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Called once, right after the module is instantiated."""

    def stop(self) -> None:
        """Called once, when the app is shutting down."""

    def on_button(self, index: int) -> bool:
        """Handle a physical button press.

        :param index: Zero-based index of the pressed button (0..3), matching
            the position in ``config["buttons"]["gpio_pins"]``.
        :returns: ``True`` if the module wants the display to be refreshed
            immediately (bypassing ``refresh_interval``), else ``False``.
        """
        return False

    # ------------------------------------------------------------------ #
    # Required rendering hook.                                           #
    # ------------------------------------------------------------------ #
    @abstractmethod
    def render(self, image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
        """Draw one frame onto ``image`` using ``draw``.

        Implementations should paint the whole frame — the canvas is
        pre-cleared to white before each call.
        """

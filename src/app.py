"""Main InkHub coordinator: config -> display -> module -> refresh loop."""

from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path
from typing import Any

from PIL import ImageDraw

from .buttons import ButtonPanel
from .config import load_config
from .display import Display
from .registry import create_module, discover_modules

_log = logging.getLogger(__name__)


class InkHubApp:
    """Owns the display, the buttons and the currently active module."""

    def __init__(
        self,
        config_path: str | Path = "config.json",
        module_name: str | None = None,
    ) -> None:
        self._config: dict[str, Any] = load_config(config_path)

        logging.getLogger().setLevel(self._config.get("log_level", "INFO"))

        self._display = Display(
            driver_name=self._config["panel_driver"],
            rotation=int(self._config.get("rotation", 0)),
        )

        discover_modules()
        selected_module = module_name or self._config["active_module"]
        module_cfg = self._config.get("modules", {}).get(selected_module, {})
        self._module = create_module(selected_module, module_cfg, self._display.size)
        _log.info("Active module: %s", selected_module)
        self._module_lock = threading.RLock()
        self._module_started = False

        self._refresh_interval = max(1, int(self._config.get("refresh_interval", 60)))
        self._wake = threading.Event()
        self._stop = threading.Event()

        btn_cfg = self._config.get("buttons", {})
        self._buttons = ButtonPanel(
            pins=btn_cfg.get("gpio_pins", [5, 6, 13, 19]),
            on_press=self._on_button,
            pull_up=bool(btn_cfg.get("pull_up", True)),
            bounce_time_ms=int(btn_cfg.get("bounce_time_ms", 50)),
        )

    # ------------------------------------------------------------------ #
    @property
    def active_module_name(self) -> str:
        """Return the currently active module name."""
        with self._module_lock:
            return self._module.name

    def _on_button(self, index: int) -> None:
        """Forward a button press to the active module and maybe refresh."""
        with self._module_lock:
            refresh = self._module.on_button(index)
        if refresh:
            _log.debug("Module requested immediate refresh")
            self._wake.set()

    def _render_and_show(self) -> None:
        """Render one frame from the active module and push it to the panel."""
        image = self._display.new_frame()
        draw = ImageDraw.Draw(image)
        with self._module_lock:
            module = self._module
            try:
                module.render(image, draw)
            except Exception:
                _log.exception("Module %r render failed", module.name)
                return
            t0 = time.monotonic()
            self._display.show(image)
        _log.debug("Full refresh in %.2fs", time.monotonic() - t0)

    def switch_module(self, module_name: str) -> bool:
        """Switch the running module and request an immediate refresh."""
        with self._module_lock:
            current_module = self._module
            if current_module.name == module_name:
                return False

            module_cfg = self._config.get("modules", {}).get(module_name, {})
            new_module = create_module(module_name, module_cfg, self._display.size)
            if self._module_started:
                new_module.start()

                try:
                    current_module.stop()
                except Exception:
                    _log.exception(
                        "Module %r stop() raised during switch",
                        current_module.name,
                    )

            self._module = new_module
            self._config["active_module"] = module_name

        _log.info("Switched active module to %s", module_name)
        self._wake.set()
        return True

    def run(self) -> None:
        """Main loop. Blocks until :meth:`stop` (or SIGINT/SIGTERM)."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: self.stop())

        with self._module_lock:
            self._module.start()
            self._module_started = True
        _log.info(
            "InkHub running (refresh every %ds). Press Ctrl+C to stop.",
            self._refresh_interval,
        )
        try:
            while not self._stop.is_set():
                self._render_and_show()
                # Rate-limit: never refresh faster than `refresh_interval`
                # unless a button press explicitly wakes us up.
                self._wake.wait(timeout=self._refresh_interval)
                self._wake.clear()
        finally:
            self._shutdown()

    def stop(self) -> None:
        """Ask the main loop to exit at its next iteration."""
        _log.info("Shutdown requested")
        self._stop.set()
        self._wake.set()

    def _shutdown(self) -> None:
        try:
            with self._module_lock:
                if self._module_started:
                    self._module.stop()
                    self._module_started = False
        except Exception:
            _log.exception("Module stop() raised")
        self._buttons.close()
        self._display.sleep()
        _log.info("InkHub stopped")

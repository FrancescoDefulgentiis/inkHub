"""Main InkHub coordinator: config -> display -> module -> event-driven updates."""

from __future__ import annotations

import logging
import queue
import signal
import threading
from pathlib import Path
from typing import Any

from .config import load_config
from .diagnostics import configure as _configure_diagnostics
from .display import Display
from .registry import available_modules, create_module, discover_modules

_log = logging.getLogger(__name__)


class InkHubApp:
    """Owns the display and the currently active module."""

    def __init__(
        self,
        config_path: str | Path = "config_files/config.json",
        module_name: str | None = None,
    ) -> None:
        self._config: dict[str, Any] = load_config(config_path)

        verbose_level_name = str(self._config.get("log_level", "INFO")).upper()
        verbose_level = logging.getLevelName(verbose_level_name)
        if not isinstance(verbose_level, int):
            verbose_level = logging.INFO
        _configure_diagnostics(
            verbose_level=verbose_level,
            quiet_level=logging.WARNING,
        )

        self._display = Display(
            driver_name=self._config["panel_driver"],
        )

        discover_modules()
        selected_module = module_name or self._config["active_module"]
        module_cfg = self._config.get("modules", {}).get(selected_module, {})
        self._module = create_module(selected_module, module_cfg, self._display.size)
        _log.info("Active module: %s", selected_module)
        self._switch_modules = self._resolve_switch_modules()
        self._module_lock = threading.RLock()
        self._module_started = False
        self._wake = threading.Event()
        self._stop = threading.Event()

    # ------------------------------------------------------------------ #
    @property
    def active_module_name(self) -> str:
        """Return the currently active module name."""
        with self._module_lock:
            return self._module.name

    @property
    def available_switch_modules(self) -> tuple[str, ...]:
        """Return the module names bound to switch buttons 1-9."""
        return self._switch_modules

    def _resolve_switch_modules(self) -> tuple[str, ...]:
        active_module = str(self._config.get("active_module", "")).strip()
        configured_modules = [
            str(name).strip() for name in self._config.get("modules", {}) if str(name).strip()
        ]
        discovered_modules = set(available_modules())
        slots: list[str] = []
        for module_name in [active_module, *configured_modules, *available_modules()]:
            if module_name and module_name in discovered_modules and module_name not in slots:
                slots.append(module_name)
            if len(slots) == 9:
                break
        return tuple(slots)

    def press_button(self, index: int) -> str:
        """Handle a virtual button press from the terminal menu."""
        if index < 9 and index < len(self._switch_modules):
            module_name = self._switch_modules[index]
            changed = self.switch_module(module_name)
            if changed:
                return f"Switched to module '{module_name}'."
            return f"Module '{module_name}' is already active."

        if index < 9:
            message = f"No module is assigned to button {index + 1}."
            _log.warning(message)
            return message

        if index == 9:
            self.press_action_button()
            return f"Action button sent to '{self.active_module_name}'."

        message = f"Ignoring unexpected button index {index}."
        _log.warning(message)
        return message

    def _consume_and_show(self) -> None:
        """Consume one image from the active module's queue and push it to the panel."""
        with self._module_lock:
            module = self._module
        try:
            image = module.image_queue.get_nowait()
        except queue.Empty:
            return
        self._display.show(image)

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

    def press_action_button(self) -> None:
        """Forward the dedicated action button to the active module."""
        with self._module_lock:
            self._module.on_action_button()
        self._wake.set()

    def run(self) -> None:
        """Main loop."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: self.stop())

        with self._module_lock:
            self._module.start()
            self._module_started = True
        _log.info("InkHub running with module-driven updates. Press Ctrl+C to stop.")
        try:
            while not self._stop.is_set():
                self._consume_and_show()
                self._wake.wait(timeout=0.05)
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
        self._display.sleep()
        _log.info("InkHub stopped")

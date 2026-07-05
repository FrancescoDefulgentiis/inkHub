"""Interactive terminal launcher menu."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
import threading
from typing import Any, Protocol

from .config import load_config
from .registry import available_modules, discover_modules

_log = logging.getLogger(__name__)


class AppController(Protocol):
    """App surface used by the terminal launcher."""

    @property
    def active_module_name(self) -> str: ...

    def switch_module(self, module_name: str) -> bool: ...

    def stop(self) -> None: ...


def start_interactive_menu(app: AppController, config_path: str | Path) -> threading.Thread:
    """Run the interactive menu on a background thread while the app is active."""
    config = load_config(config_path)
    thread = threading.Thread(
        target=_menu_loop,
        args=(app, Path(config_path), config),
        name="inkhub-terminal-menu",
        daemon=True,
    )
    thread.start()
    return thread


def _menu_loop(app: AppController, config_path: Path, config: dict[str, Any]) -> None:
    print()
    print("InkHub terminal controls are active. Use 1-5 to switch modules, q/Esc to quit.")

    while True:
        discover_modules()
        discovered = available_modules()
        slots = _module_slots(config, discovered)
        _print_menu(config, config_path, slots, app.active_module_name)
        key = _read_key().lower()
        print()

        if key in {"q", "\x1b"}:
            print("Stopping InkHub.")
            app.stop()
            return

        if key in {"1", "2", "3", "4", "5"}:
            slot_index = int(key) - 1
            if slot_index < len(slots):
                module_name = slots[slot_index]
                try:
                    changed = app.switch_module(module_name)
                except Exception:
                    _log.exception("Failed to switch to module %r", module_name)
                    print(f"Failed to switch to '{module_name}'. Check the logs for details.")
                else:
                    if changed:
                        print(f"Switched to module '{module_name}'.")
                    else:
                        print(f"Module '{module_name}' is already active.")
                continue

            print(f"Slot {key} is not assigned yet.")
            _wait_for_keypress()
            continue

        if key == "c":
            _print_config_summary(config, config_path, app.active_module_name)
            _wait_for_keypress()
            continue

        if key == "d":
            _print_diagnostics(config, config_path, discovered, app.active_module_name)
            _wait_for_keypress()
            continue

        if key in {"h", "?"}:
            _print_help()
            _wait_for_keypress()
            continue

        print(f"Unsupported key: {key!r}")
        _wait_for_keypress()


def _module_slots(config: dict[str, Any], discovered: list[str]) -> list[str]:
    active_module = str(config.get("active_module", "")).strip()
    configured_modules = [
        str(name).strip() for name in config.get("modules", {}) if str(name).strip()
    ]

    slots: list[str] = []
    for module_name in [active_module, *configured_modules, *discovered]:
        if module_name and module_name in discovered and module_name not in slots:
            slots.append(module_name)
        if len(slots) == 5:
            break
    return slots


def _print_menu(
    config: dict[str, Any],
    config_path: Path,
    slots: list[str],
    active_module_name: str,
) -> None:
    print()
    print("=" * 64)
    print("InkHub terminal launcher")
    print(f"Config   : {config_path.resolve()}")
    print(f"Running  : {active_module_name}")
    print(f"Default  : {config.get('active_module', '<unset>')}")
    print("-" * 64)
    print("Modules")
    for slot in range(5):
        if slot < len(slots):
            label = slots[slot]
            suffix = " (running)" if label == active_module_name else ""
            print(f"  {slot + 1}. {label}{suffix}")
        else:
            print(f"  {slot + 1}. [empty slot]")
    print("-" * 64)
    print("Extra actions")
    print("  C. Show config summary")
    print("  D. Show diagnostics")
    print("  H. Show help")
    print("  Q / Esc. Quit")
    print("=" * 64)
    print("Press a key...", end="", flush=True)


def _print_config_summary(
    config: dict[str, Any],
    config_path: Path,
    active_module_name: str,
) -> None:
    module_names = sorted(str(name) for name in config.get("modules", {}))
    button_cfg = config.get("buttons", {})
    print()
    print("Config summary")
    print("-" * 64)
    print(f"Path             : {config_path.resolve()}")
    print(f"Panel driver     : {config.get('panel_driver', '<unset>')}")
    print(f"Running module   : {active_module_name}")
    print(f"Default module   : {config.get('active_module', '<unset>')}")
    print(f"Configured       : {', '.join(module_names) if module_names else '<none>'}")
    print(f"Refresh interval : {config.get('refresh_interval', '<unset>')}s")
    print(f"Rotation         : {config.get('rotation', '<unset>')}")
    print(f"Log level        : {config.get('log_level', '<unset>')}")
    print(f"GPIO pins        : {button_cfg.get('gpio_pins', [])}")
    print(f"Pull-up          : {button_cfg.get('pull_up', True)}")
    print(f"Debounce         : {button_cfg.get('bounce_time_ms', 50)}ms")


def _print_diagnostics(
    config: dict[str, Any],
    config_path: Path,
    discovered: list[str],
    active_module_name: str,
) -> None:
    configured_modules = sorted(str(name) for name in config.get("modules", {}))
    print()
    print("Diagnostics")
    print("-" * 64)
    print(f"Python           : {sys.version.split()[0]}")
    print(f"Platform         : {sys.platform}")
    print(f"Working dir      : {Path.cwd()}")
    print(f"Config exists    : {config_path.resolve().is_file()}")
    print(f"Running module   : {active_module_name}")
    print(f"Configured mods  : {configured_modules if configured_modules else []}")
    print(f"Discovered mods  : {discovered if discovered else []}")
    print(f"Running available: {active_module_name in discovered}")
    print(f"TTY stdin/stdout : {sys.stdin.isatty()}/{sys.stdout.isatty()}")
    print(f"OS mode          : {os.name}")


def _print_help() -> None:
    print()
    print("Launcher help")
    print("-" * 64)
    print("1-5 : switch to the module shown in that slot")
    print("C   : print the config summary")
    print("D   : print diagnostics useful while wiring modules and hardware")
    print("H   : show this help")
    print("Q   : stop the app and quit")
    print("Esc : stop the app and quit")


def _wait_for_keypress() -> None:
    print()
    print("Press any key to return to the launcher...", end="", flush=True)
    _read_key()
    print()


def _read_key() -> str:
    if os.name == "nt":
        import msvcrt

        while True:
            key = msvcrt.getwch()
            if key in {"\x00", "\xe0"}:
                msvcrt.getwch()
                continue
            return key

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        if key != "\x1b":
            return key

        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not ready:
            return key

        sequence = [key]
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if not ready:
                break
            sequence.append(sys.stdin.read(1))
        return "".join(sequence)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

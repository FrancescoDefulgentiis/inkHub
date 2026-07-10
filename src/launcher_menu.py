from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, Protocol

from .config import load_config
from . import diagnostics
from .registry import available_modules

_log = logging.getLogger(__name__)


class AppController(Protocol):
    """App surface used by the terminal launcher."""

    @property
    def active_module_name(self) -> str: ...

    @property
    def available_switch_modules(self) -> tuple[str, ...]: ...

    def press_button(self, index: int) -> str: ...

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
    print("InkHub terminal controls are active. Use 1-9 to switch modules, 0 for action,")
    print("D to toggle verbose logs, q/Esc to quit.")

    while True:

        slots = list(app.available_switch_modules)
        _print_menu(config, config_path, slots, app.active_module_name)
        key = _read_key().lower()
        print()

        match key:
            case "t" | "\x02":
                if os.environ.get("TMUX"):
                    subprocess.run(["tmux", "detach-client"])
                    return
            case "q" | "\x1b":
                print("Stopping InkHub.")
                app.stop()
                return
            case "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9":
                try:
                    button_index = int(key)
                    if button_index == 0:
                        message = app.press_button(9)
                    else:
                        message = app.press_button(button_index - 1)
                except Exception:
                    _log.exception("Failed to handle virtual button %s", key)
                    print(f"Failed to handle button {key}. Check the logs for details.")
                else:
                    print(message)
            case "c":
                _print_config_summary(config, config_path, app.active_module_name)
                _wait_for_keypress()
            case "d":
                enabled = diagnostics.toggle()
                if enabled:
                    print("Diagnostics ON — verbose logging enabled.")
                    _print_diagnostics(config, config_path, slots, app.active_module_name)
                else:
                    print("Diagnostics OFF — verbose logging disabled.")
                _wait_for_keypress()
            case "h" | "?":
                _print_help()
                _wait_for_keypress()
            case _:
                print(f"Unsupported key: {key!r}")
                _wait_for_keypress()

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
    print("-" * 64)
    print("Switch buttons")
    for slot in range(9):
        if slot < len(slots):
            label = slots[slot]
            suffix = " (running)" if label == active_module_name else ""
            print(f"  {slot + 1}. {label}{suffix}")
        else:
            print(f"  {slot + 1}. [empty slot]")
    print("  0. Action button for the running module")
    print("-" * 64)
    print("Extra actions")
    diag_state = "ON" if diagnostics.is_enabled() else "OFF"
    print("  C. Show config summary")
    print(f"  D. Toggle diagnostics / verbose logs (currently {diag_state})")
    print("  H. Show help")
    print("  Q / Esc. Quit")
    print("=" * 64)
    print("Press a key...", end="", flush=True)


def _print_config_summary(
    config: dict[str, Any],
    config_path: Path,
    active_module_name: str,
) -> None:
    module_names = available_modules()
    print()
    print("Config summary")
    print("-" * 64)
    print(f"Path             : {config_path.resolve()}")
    print(f"Panel driver     : {config.get('panel_driver', '<unset>')}")
    print(f"Running module   : {active_module_name}")
    print(f"Discovered       : {', '.join(module_names) if module_names else '<none>'}")
    print(f"Log level        : {config.get('log_level', '<unset>')}")
    print("Control mode     : terminal menu only")
    print("Button roles     : 1-9 switch modules, 0 triggers the running module")


def _print_diagnostics(
    config: dict[str, Any],
    config_path: Path,
    switch_modules: list[str],
    active_module_name: str,
) -> None:
    discovered = available_modules()
    print()
    print("Diagnostics")
    print("-" * 64)
    print(f"Python           : {sys.version.split()[0]}")
    print(f"Platform         : {sys.platform}")
    print(f"Working dir      : {Path.cwd()}")
    print(f"Config exists    : {config_path.resolve().is_file()}")
    print(f"Running module   : {active_module_name}")
    print(f"Discovered mods  : {discovered if discovered else []}")
    print(f"Switch modules   : {switch_modules if switch_modules else []}")
    print(f"Running slotted  : {active_module_name in switch_modules}")
    print(f"TTY stdin/stdout : {sys.stdin.isatty()}/{sys.stdout.isatty()}")
    print(f"OS mode          : {os.name}")
    print(f"Diagnostics flag : {'ON' if diagnostics.is_enabled() else 'OFF'}")


def _print_help() -> None:
    print()
    print("Launcher help")
    print("-" * 64)
    print("1-9 : switch to the module shown in that slot")
    print("0   : send the dedicated action button to the running module")
    print("C   : print the config summary")
    print("D   : toggle diagnostics — enables/disables verbose logs and,")
    print("      when turning ON, prints the diagnostics snapshot")
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

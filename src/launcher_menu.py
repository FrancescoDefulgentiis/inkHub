"""Interactive terminal launcher menu."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Any

from .config import load_config
from .registry import available_modules, discover_modules


@dataclass(frozen=True)
class LauncherSelection:
    """Terminal launcher outcome."""

    action: str
    module_name: str | None = None


def prompt_for_selection(config_path: str | Path) -> LauncherSelection:
    """Show the interactive launcher menu until the user runs or quits."""
    config = load_config(config_path)

    while True:
        discover_modules()
        discovered = available_modules()
        slots = _module_slots(config, discovered)
        _print_menu(config, Path(config_path), slots)
        key = _read_key().lower()
        print()

        if key in {"q", "\x1b"}:
            print("Closing InkHub launcher.")
            return LauncherSelection(action="quit")

        if key in {"1", "2", "3", "4", "5"}:
            slot_index = int(key) - 1
            if slot_index < len(slots):
                module_name = slots[slot_index]
                print(f"Launching module '{module_name}'.")
                return LauncherSelection(action="run", module_name=module_name)
            print(f"Slot {key} is not assigned yet.")
            _wait_for_keypress()
            continue

        if key == "c":
            _print_config_summary(config, Path(config_path))
            _wait_for_keypress()
            continue

        if key == "d":
            _print_diagnostics(config, Path(config_path), discovered)
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
    config: dict[str, Any], config_path: Path, slots: list[str]
) -> None:
    print()
    print("=" * 64)
    print("InkHub terminal launcher")
    print(f"Config : {config_path.resolve()}")
    print(f"Active : {config.get('active_module', '<unset>')}")
    print("-" * 64)
    print("Modules")
    for slot in range(5):
        if slot < len(slots):
            label = slots[slot]
            suffix = " (active)" if label == config.get("active_module") else ""
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
    print("Press a key to continue...", end="", flush=True)


def _print_config_summary(config: dict[str, Any], config_path: Path) -> None:
    module_names = sorted(str(name) for name in config.get("modules", {}))
    button_cfg = config.get("buttons", {})
    print()
    print("Config summary")
    print("-" * 64)
    print(f"Path             : {config_path.resolve()}")
    print(f"Panel driver     : {config.get('panel_driver', '<unset>')}")
    print(f"Active module    : {config.get('active_module', '<unset>')}")
    print(f"Configured       : {', '.join(module_names) if module_names else '<none>'}")
    print(f"Refresh interval : {config.get('refresh_interval', '<unset>')}s")
    print(f"Rotation         : {config.get('rotation', '<unset>')}")
    print(f"Log level        : {config.get('log_level', '<unset>')}")
    print(f"GPIO pins        : {button_cfg.get('gpio_pins', [])}")
    print(f"Pull-up          : {button_cfg.get('pull_up', True)}")
    print(f"Debounce         : {button_cfg.get('bounce_time_ms', 50)}ms")


def _print_diagnostics(
    config: dict[str, Any], config_path: Path, discovered: list[str]
) -> None:
    active_module = str(config.get("active_module", "")).strip()
    configured_modules = sorted(str(name) for name in config.get("modules", {}))
    print()
    print("Diagnostics")
    print("-" * 64)
    print(f"Python           : {sys.version.split()[0]}")
    print(f"Platform         : {sys.platform}")
    print(f"Working dir      : {Path.cwd()}")
    print(f"Config exists    : {config_path.resolve().is_file()}")
    print(f"Configured mods  : {configured_modules if configured_modules else []}")
    print(f"Discovered mods  : {discovered if discovered else []}")
    print(f"Active available : {active_module in discovered}")
    print(f"TTY stdin/stdout : {sys.stdin.isatty()}/{sys.stdout.isatty()}")
    print(f"OS mode          : {os.name}")


def _print_help() -> None:
    print()
    print("Launcher help")
    print("-" * 64)
    print("1-5 : launch the module shown in that slot")
    print("C   : print the config summary")
    print("D   : print diagnostics useful while wiring modules and hardware")
    print("H   : show this help")
    print("Q   : quit the launcher")
    print("Esc : quit the launcher")


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

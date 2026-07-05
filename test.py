#!/usr/bin/env python3
"""Hardware/software diagnostics + live display test for Waveshare e-paper."""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, __version__ as PILLOW_VERSION

LOG = logging.getLogger("epd_test")


def configure_logging(log_file: Path, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    LOG.info("Logging to %s", log_file)


def run_command(cmd: list[str]) -> None:
    LOG.debug("Running command: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        LOG.exception("Failed running command: %s", " ".join(cmd))
        return

    LOG.info("Command exit %s: %s", proc.returncode, " ".join(cmd))
    if proc.stdout.strip():
        LOG.info("stdout:\n%s", proc.stdout.strip())
    if proc.stderr.strip():
        LOG.warning("stderr:\n%s", proc.stderr.strip())


def log_basic_diagnostics() -> None:
    LOG.info("===== BASIC DIAGNOSTICS =====")
    LOG.info("Timestamp: %s", datetime.now().isoformat())
    LOG.info("Python: %s", sys.version.replace("\n", " "))
    LOG.info("Executable: %s", sys.executable)
    LOG.info("Platform: %s", platform.platform())
    LOG.info("Machine: %s", platform.machine())
    LOG.info("Hostname: %s", platform.node())
    LOG.info("Current working directory: %s", Path.cwd())
    LOG.info("Pillow version: %s", PILLOW_VERSION)
    LOG.info("PID: %s", os.getpid())

    for path in ("/dev/spidev0.0", "/dev/spidev0.1", "/dev/gpiomem", "/dev/gpiochip0"):
        p = Path(path)
        if p.exists():
            LOG.info("Device present: %s", path)
        else:
            LOG.warning("Device missing: %s", path)


def log_pi_commands() -> None:
    LOG.info("===== RASPBERRY PI COMMAND DIAGNOSTICS =====")
    commands: Iterable[list[str]] = (
        ["uname", "-a"],
        ["cat", "/etc/os-release"],
        ["ls", "-l", "/dev/spidev0.0"],
        ["ls", "-l", "/dev/spidev0.1"],
        ["lsmod"],
        ["raspi-gpio", "get", "8", "17", "18", "24", "25"],
        ["vcgencmd", "get_throttled"],
        ["vcgencmd", "measure_temp"],
    )
    for cmd in commands:
        run_command(list(cmd))


def build_frame(width: int, height: int, cycle: int, total: int) -> Image.Image:
    image = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    border_thickness = 10 + (cycle % 3) * 8

    draw.rectangle((0, 0, width - 1, height - 1), outline=0, width=2)
    draw.rectangle(
        (border_thickness, border_thickness, width - 1 - border_thickness, height - 1 - border_thickness),
        outline=0,
        width=2,
    )

    lines = [
        "InkHub EPD test.py",
        "Status: ALIVE",
        f"Frame: {cycle}/{total}",
        f"Time: {now}",
        "Board: Raspberry Pi Zero 2 W",
        "HAT: e-Paper Driver HAT Rev2.3",
        "Panel: epd7in5_V2 (800x480)",
        "If this changes each cycle, SPI/GPIO are working.",
    ]
    y = 20
    for line in lines:
        draw.text((20, y), line, font=font, fill=0)
        y += 22

    bar_w = width - 40
    progress = int(bar_w * cycle / total)
    draw.rectangle((20, height - 50, 20 + bar_w, height - 25), outline=0, width=2)
    draw.rectangle((22, height - 48, 22 + max(0, progress - 4), height - 27), fill=0)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description="Waveshare e-paper live diagnostic test")
    parser.add_argument("--driver", default="epd7in5_V2", help="Driver module name inside waveshare_epd")
    parser.add_argument("--cycles", type=int, default=3, help="Number of screen updates to perform")
    parser.add_argument("--interval", type=float, default=8.0, help="Seconds between updates")
    parser.add_argument("--log-file", default="test.log", help="Log file path")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    configure_logging(Path(args.log_file), verbose=args.verbose)
    log_basic_diagnostics()
    log_pi_commands()

    epd = None
    epdconfig = None
    try:
        LOG.info("Importing driver module waveshare_epd.%s", args.driver)
        driver_module = importlib.import_module(f"waveshare_epd.{args.driver}")
        epdconfig = importlib.import_module("waveshare_epd.epdconfig")

        LOG.info("Instantiating EPD object")
        epd = driver_module.EPD()
        LOG.info("EPD dimensions reported by driver: %sx%s", epd.width, epd.height)
        LOG.info("Starting panel init()")
        init_result = epd.init()
        LOG.info("epd.init() returned: %r", init_result)
        if init_result == -1:
            raise RuntimeError("epd.init() failed with -1 (module_init failure)")

        LOG.info("Clearing panel")
        epd.Clear()

        cycles = max(1, args.cycles)
        for cycle in range(1, cycles + 1):
            frame_start = time.monotonic()
            LOG.info("Rendering cycle %d/%d", cycle, cycles)
            image = build_frame(epd.width, epd.height, cycle, cycles)
            LOG.debug("Converting image buffer for panel")
            buffer = epd.getbuffer(image)
            LOG.debug("Pushing frame to display")
            epd.display(buffer)
            frame_time = time.monotonic() - frame_start
            LOG.info("Cycle %d done in %.2fs", cycle, frame_time)

            if cycle < cycles:
                LOG.info("Sleeping %.1fs before next update", args.interval)
                time.sleep(max(0.0, args.interval))

        LOG.info("Display test completed successfully")
        return 0

    except Exception as exc:
        LOG.error("Diagnostic test failed: %s", exc)
        LOG.debug("Stack trace:\n%s", traceback.format_exc())
        return 1

    finally:
        if epd is not None:
            try:
                LOG.info("Putting panel to sleep")
                epd.sleep()
            except Exception:
                LOG.exception("Failed to put panel to sleep")
        if epdconfig is not None:
            try:
                LOG.info("Calling epdconfig.module_exit(cleanup=True)")
                epdconfig.module_exit(cleanup=True)
            except Exception:
                LOG.exception("Failed during epdconfig.module_exit(cleanup=True)")


if __name__ == "__main__":
    raise SystemExit(main())

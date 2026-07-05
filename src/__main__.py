"""``python -m inkhub`` entry point."""

from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="inkhub", description="Modular e-ink dashboard")
    parser.add_argument(
        "-c", "--config", default="config.json",
        help="Path to config file (default: config.json)",
    )
    parser.add_argument(
        "--no-menu",
        action="store_true",
        help="Skip the interactive terminal launcher menu",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    from .app import InkHubApp
    from .launcher_menu import prompt_for_selection

    try:
        module_name = None
        use_menu = not args.no_menu
        if use_menu and sys.stdin.isatty() and sys.stdout.isatty():
            selection = prompt_for_selection(args.config)
            if selection.action == "quit":
                return 0
            module_name = selection.module_name

        InkHubApp(args.config, module_name=module_name).run()
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.getLogger("inkhub").exception("Fatal error")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

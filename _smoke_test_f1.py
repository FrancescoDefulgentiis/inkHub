"""Smoke test for the Formula 1 module.

Renders both views (weekend + championship) to PNG files without needing the
physical e-ink panel, then prints a summary of the fetched data.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the ``src`` package importable.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.registry import create_module, discover_modules  # noqa: E402


def main() -> int:
    discover_modules()

    size = (800, 480)  # matches epd7in5
    module = create_module("formula1", {"view": "weekend"}, size)

    # First render: default view.
    weekend = module.render()
    weekend.save(ROOT / "_smoke_weekend.png")
    print("Wrote _smoke_weekend.png", weekend.size, weekend.mode)

    # Toggle to championship and re-render.
    module.on_action_button()
    championship = module.render()
    championship.save(ROOT / "_smoke_championship.png")
    print("Wrote _smoke_championship.png", championship.size, championship.mode)

    race = module._race
    ch = module._championship
    if race is not None:
        info = race.info
        print(f"Race: {info.season} R{info.round} - {info.name}")
        print(f"  Circuit: {info.circuit} ({info.country}) on {info.date}")
        print(f"  Results: {len(race.results)}")
        for r in race.results[:3]:
            print(
                f"    P{r.position} {r.driver_name} ({r.constructor}) "
                f"{r.time_text} - {r.points} pts"
            )
        if race.fastest_lap:
            print(
                f"  Fastest lap: {race.fastest_lap.driver_name} "
                f"{race.fastest_lap.fastest_lap_time}"
            )
        if race.pole:
            print(f"  Pole: {race.pole.driver_name}")
    else:
        print("Race data unavailable")

    if ch is not None:
        print(f"Championship: {ch.season} after round {ch.round}")
        print(f"  Drivers: {len(ch.drivers)}, Constructors: {len(ch.constructors)}")
        for d in ch.drivers[:3]:
            print(f"    {d.position}. {d.driver_name} ({d.constructor}) {d.points}")
        for c in ch.constructors[:3]:
            print(f"    {c.position}. {c.constructor} {c.points} ({c.wins} wins)")
    else:
        print("Championship data unavailable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

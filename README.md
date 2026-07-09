# InkHub

InkHub is a versatile hardware platform that integrates the high-contrast clarity of e-ink technology with the processing power of a Raspberry Pi. At its core, the project focuses on modular utility. Rather than functioning as a closed system, InkHub is designed to be an extensible ecosystem. By prioritizing open customizability and collaborative input, the device allows for a wide range of applications.

for more information about the project birth and upkeep come check out my [blog posts about it](https://francescodefulgentiis.github.io/#/blog/InkHub)

Built-in modules:

| Module          | What it shows                                             |
| --------------- | --------------------------------------------------------- |
| `dashboard`     | Clock + local weather + quote of the day                  |
## Quick start

```bash
git clone https://github.com/FrancescoDefulgentiis/inkHub.git
cd inkHub

# 1. Create and activate a virtualenv
python -m venv .venv
source .venv/bin/activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install the Waveshare e-paper driver (drops waveshare_epd/ in the repo root)
curl -L https://github.com/waveshareteam/e-Paper/archive/refs/heads/master.tar.gz \
  | tar -xz --strip-components=4 "e-Paper-master/RaspberryPi_JetsonNano/python/lib/waveshare_epd"

# 4. Adjust src/config.json to match your panel and preferences(optional)

# 5. Run
python run.py
```

## Configuration

The main configuration lives at [`src/config.json`](src/config.json):

```json
{
  "panel_driver": "epd7in5",
  "active_module": "dashboard",
  "rotation": 0,
  "log_level": "INFO",
  "switch_modules": ["dashboard", "weather", "formula1", "ytmusic", "photo_gallery"]
}
```

| Key              | Description                                                                 |
| ---------------- | --------------------------------------------------------------------------- |
| `panel_driver`   | Module name inside `waveshare_epd` for your panel (e.g. `epd7in5`, `epd4in2`) |
| `active_module`  | Which module to render at startup                                           |
| `switch_modules` | Up to nine modules bound to buttons 1–9 of the interactive launcher menu    |
| `log_level`      | Standard Python logging level                                               |

Each module also has its own `config.json` next to its `__init__.py` (for example, `src/modules/weather/config.json`). Module-specific settings always live there — the root config only handles global options.

## Running headless

If you don't need the interactive terminal launcher:

```bash
python run.py --no-menu
```

## Built-in modules

Each screen ("module") lives in its own folder under `src/modules/` and is discovered automatically at startup. Adding a new view is as simple as dropping a new folder in there — no wiring required.

InkHub ships with one module out of the box:

| Module      | What it shows                            |
| ----------- | ---------------------------------------- |
| `dashboard` | Clock + local weather + quote of the day |

Looking for more? The [inkhub-modules](https://github.com/FrancescoDefulgentiis/inkhub-modules) repository has a growing collection of ready-to-use modules, each with its own documentation. You're also welcome to build your own and contribute it there — check the wiki article on [How to add a new module](https://github.com/FrancescoDefulgentiis/inkHub/wiki) to get started.

## Repository layout

```
inkHub/
├── run.py                  # Entry point
├── requirements.txt
├── src/
│   ├── config.json         # Root InkHub configuration
│   ├── __main__.py         # `python -m src` entry point
│   ├── app.py              # Main coordinator loop
│   ├── display.py          # Thin wrapper over waveshare_epd
│   ├── registry.py         # Module discovery and factory
│   ├── module.py           # Base Module class
│   ├── launcher_menu.py    # Interactive terminal launcher
│   ├── diagnostics.py      # Logging setup
│   └── modules/
│       └── dashboard/
└── waveshare_epd/          # Not in git — install from upstream (see above)
```

## Development notes

Modules self-register via the `@register_module("name")` decorator. The registry imports every subpackage of `src.modules` at startup, so creating a new folder with a decorated class is all you need to make a module available.

If you have questions or ideas, feel free to open an issue — contributions are always appreciated.

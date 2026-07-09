# InkHub

A modular e-ink dashboard for a Waveshare panel connected to a Raspberry Pi.
Each screen ("module") lives in its own folder under `src/modules/` and is
picked up automatically at startup — dropping a new folder in there is all it
takes to add a new view.

Built-in modules:

| Module          | What it shows                                             |
| --------------- | --------------------------------------------------------- |
| `dashboard`     | Clock + local weather + quote of the day                  |
| `weather`       | Detailed current conditions and 7-day forecast            |
| `formula1`      | Next race weekend and driver / constructor standings      |
| `ytmusic`       | Now-playing + up-next queue from a YouTube Music account  |
| `photo_gallery` | Rotating photo gallery with a small web uploader UI       |

## Quick start

```bash
git clone https://github.com/FrancescoDefulgentiis/inkHub.git
cd inkHub

# 1. Create and activate a virtualenv
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install the Waveshare e-paper driver (see next section)

# 4. Adjust src/config.json to match your panel and preferences

# 5. Run
python run.py
```

## Waveshare e-paper driver

InkHub does not ship the Waveshare Python driver itself — it imports it as a
regular Python package called `waveshare_epd`. Grab the pinned upstream copy
that InkHub was developed against here:

<https://github.com/waveshareteam/e-Paper/tree/702def06bcb75983c98b0f9d25d43c552c248eb0/RaspberryPi%26JetsonNano/python/lib/waveshare_epd>

The simplest install is to drop the whole `waveshare_epd/` folder from that
tree into the repository root (it is already git-ignored) or anywhere on your
`PYTHONPATH`:

```bash
# From the repo root
git clone --depth 1 https://github.com/waveshareteam/e-Paper.git /tmp/e-Paper
cp -r "/tmp/e-Paper/RaspberryPi&JetsonNano/python/lib/waveshare_epd" .
```

On a Raspberry Pi you also need the system-side SPI / GPIO bits the driver
depends on — follow the instructions in the upstream `e-Paper` repository.

## Configuration

The root config lives at [`src/config.json`](src/config.json) and looks like:

```json
{
  "panel_driver": "epd7in5",
  "active_module": "dashboard",
  "rotation": 0,
  "log_level": "INFO",
  "switch_modules": ["dashboard", "weather", "formula1", "ytmusic", "photo_gallery"]
}
```

- `panel_driver` — module name inside `waveshare_epd` for your panel
  (e.g. `epd7in5`, `epd7in5_V2`, `epd4in2`, …).
- `active_module` — which module to render at startup.
- `switch_modules` — up to nine modules bound to buttons 1-9 of the
  interactive launcher menu.
- `log_level` — standard Python logging level.

Every module has its own `config.json` sitting next to its `__init__.py`
(e.g. `src/modules/weather/config.json`). Edit those to tweak per-module
behaviour — the root config never holds module-specific settings.

## Module-specific setup

- **YouTube Music** — needs a `browser.json` credentials file. See
  [`src/modules/ytmusic/README.md`](src/modules/ytmusic/README.md).
- **Photo Gallery** — spins up a small Flask uploader on port 5000. Full
  guide in [`src/modules/photo_gallery/SETUP.md`](src/modules/photo_gallery/SETUP.md).

## Running headless

```bash
python run.py --no-menu           # skip the interactive terminal launcher
python run.py -c path/to/other.json
```

A minimal systemd unit is documented in the photo-gallery setup guide and
works for InkHub as a whole.

## Repository layout

```
inkHub/
├── run.py                  # tiny entry-point shim
├── requirements.txt
├── src/
│   ├── config.json         # root InkHub configuration
│   ├── __main__.py         # `python -m src` entry point
│   ├── app.py              # main coordinator loop
│   ├── display.py          # thin wrapper over waveshare_epd
│   ├── registry.py         # module discovery + factory
│   ├── module.py           # base Module class
│   ├── launcher_menu.py    # interactive terminal launcher
│   ├── diagnostics.py      # logging setup
│   └── modules/
│       ├── dashboard/
│       ├── formula1/
│       ├── photo_gallery/
│       ├── weather/
│       └── ytmusic/
└── waveshare_epd/          # NOT in git — install from upstream (see above)
```

## Development notes

- Modules self-register via the `@register_module("name")` decorator; the
  registry imports every submodule of `src.modules` at startup so adding a
  new folder is enough.
- `__pycache__/`, `*.pyc`, `.venv/`, `browser.json`, `oauth.json`,
  `photo_gallery/` (user uploads), and the vendored `waveshare_epd/` are all
  git-ignored — do not commit them.

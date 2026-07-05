# InkHub

A tiny, modular e-ink dashboard for the **Raspberry Pi Zero 2W** driving a
Waveshare e-Paper HAT (Rev 2.3). InkHub is deliberately minimal: a display
wrapper, a button handler, a main loop, and a **Service Blueprint** that lets
you drop in new "screens" (modules) with a single file.

Ships with one reference module — a digital `clock` — so it runs out of the
box.

---

## Hardware

| Piece            | Notes                                              |
|------------------|----------------------------------------------------|
| Raspberry Pi     | Zero 2W, Raspberry Pi OS Lite 64-bit (Bookworm)    |
| Display driver   | Waveshare e-Paper HAT Rev 2.3                      |
| Panel            | Any Waveshare panel supported by `waveshare_epd`   |
| Buttons          | 4× momentary switches → BCM GPIO **5, 6, 13, 19**, pulled up, active-low |

The Waveshare Python driver is expected to live in `./waveshare_epd/` at the
repo root (vendored on-device, not committed). The concrete driver module
(e.g. `epd7in5_V2`) is selected in `config.json`.

---

## Install & run

```bash
# 1. Enable SPI (once):  sudo raspi-config  →  Interface Options → SPI → Enable
# 2. Create venv & install deps (already done in your setup):
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Drop the vendored Waveshare driver into ./waveshare_epd/
#    (from https://github.com/waveshareteam/e-Paper)

# 4. Edit config.json — at minimum set "panel_driver" to your panel:
#    e.g. "epd7in5_V2", "epd2in13_V4", "epd4in2_V2", ...

# 5. Run:
python -m inkhub
```

Stop with `Ctrl+C`. The panel is put to sleep on shutdown.

To auto-start at boot, wrap `python -m inkhub` in a `systemd` unit.

---

## `config.json`

```jsonc
{
  "panel_driver": "epd7in5_V2",   // module name inside waveshare_epd/
  "active_module": "clock",       // which module to display
  "refresh_interval": 60,         // seconds between full refreshes (min)
  "rotation": 0,                  // 0 / 90 / 180 / 270
  "buttons": {
    "gpio_pins": [5, 6, 13, 19],
    "pull_up": true,
    "bounce_time_ms": 50
  },
  "log_level": "INFO",
  "modules": {
    "clock": { "time_format": "%H:%M", "date_format": "%A, %d %B %Y" }
  }
}
```

E-ink full refreshes are slow (2–4 s) and wear the panel — InkHub never
refreshes more often than `refresh_interval`, unless a module explicitly
returns `True` from `on_button()`.

---

## Adding a new module — the Service Blueprint

A module is any subclass of `inkhub.module.Module` registered with the
`@register_module("<name>")` decorator. That's the entire contract.

1. Create `inkhub/modules/weather.py`:

    ```python
    from PIL import Image, ImageDraw
    from ..module import Module
    from ..registry import register_module

    @register_module("weather")
    class WeatherModule(Module):
        """Draws the current weather."""

        def render(self, image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
            draw.text((10, 10), "Weather goes here", fill=0)

        # Optional hooks:
        # def start(self): ...
        # def stop(self):  ...
        # def on_button(self, index: int) -> bool: return False
    ```

2. Add its config block (optional) to `config.json`:

    ```json
    "modules": { "weather": { "city": "Bologna" } }
    ```

3. Point `"active_module"` at `"weather"` and restart.

That's it. No registration lists, no imports elsewhere — the registry
discovers everything under `inkhub/modules/` at start-up.

### What your module gets

- `self.width`, `self.height` — panel dimensions in pixels.
- `self.config` — your block from `config.json["modules"][<name>]`.
- A pre-cleared white 1-bit `PIL.Image` and a matching `ImageDraw` in
  `render()`. Just paint the whole frame; InkHub handles the rest.

---

## Layout

```
inkhub/
  __init__.py
  __main__.py       # `python -m inkhub`
  app.py            # Main coordinator + refresh loop
  config.py         # JSON loader
  display.py        # Wrapper around waveshare_epd
  buttons.py        # gpiozero button panel
  module.py         # Abstract Service Blueprint
  registry.py       # @register_module + factory
  modules/
    clock.py        # Reference module
config.json
requirements.txt
```

---

## Manual verification checklist

After first install on the Pi, please confirm:

- [ ] **SPI is enabled** — `ls /dev/spidev*` shows `spidev0.0`
      (`sudo raspi-config` → Interface Options → SPI).
- [ ] **Waveshare driver present** — `./waveshare_epd/` exists and contains
      the module named in `config.json`'s `"panel_driver"`
      (e.g. `waveshare_epd/epd7in5_V2.py`).
- [ ] **`"panel_driver"` matches your panel** — running `python -m inkhub`
      logs `Panel ready: WxH …`; verify W×H matches your hardware.
- [ ] **Buttons wired to BCM 5, 6, 13, 19** with the other leg to GND
      (pull-up = active-low). Press one and confirm `Button N pressed`
      appears in the log at `DEBUG` level.
- [ ] **User in the `gpio` and `spi` groups** — `id $USER` should list both;
      otherwise run under `sudo` or add with `sudo usermod -aG gpio,spi $USER`.
- [ ] **Clock renders and updates** every `refresh_interval` seconds.

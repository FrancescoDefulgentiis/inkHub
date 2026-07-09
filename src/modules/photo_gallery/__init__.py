"""Photo Gallery module — displays and manages a rotating gallery of photos on e-ink display."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw

from ...module import Module
from ...registry import register_module

_log = logging.getLogger(__name__)

# Default config
DEFAULT_CHANGE_RATE = 60  # seconds
DEFAULT_DISPLAY_MODE = "stretched"  # "full_screen", "stretched", "bordered"
GALLERY_DIR = Path("photo_gallery")
MODULE_DIR = Path(__file__).resolve().parent
LOCAL_CONFIG_FILE = MODULE_DIR / "config.json"
QR_SVG_FILE = MODULE_DIR / "qr.svg"


@register_module("photo_gallery")
class PhotoGallery(Module):
    """Display a rotating gallery of photos on the e-ink display."""

    def __init__(self, config: Mapping[str, Any], size: tuple[int, int]) -> None:
        super().__init__(config, size)
        _log.info(
            "Initialising PhotoGallery (size=%dx%d, change_rate=%ss, display_mode=%s)",
            size[0],
            size[1],
            (config or {}).get("change_rate", DEFAULT_CHANGE_RATE),
            (config or {}).get("display_mode", DEFAULT_DISPLAY_MODE),
        )
        self.gallery_dir = GALLERY_DIR
        self._setup_gallery_dir()

        self._current_photo_index = 0
        self._photos: list[Path] = []
        self._last_rotation_time = time.time()
        self._lock = threading.Lock()
        self._view_lock = threading.Lock()
        self._view: str = "gallery"
        self._qr_image_cache: Image.Image | None = None

        self._load_photos()
        self._web_server: Any = None

    def start(self) -> None:
        """Start the photo gallery module and web server."""
        _log.info("Starting PhotoGallery module")
        super().start()

        # Start the web server if enabled
        web_server_config = self.config.get("web_server", {})
        if not web_server_config.get("enabled", True):
            _log.info("Photo Gallery web server disabled via config")
            return

        try:
            from .launcher import start_gallery_web_server

            host = web_server_config.get("host", "0.0.0.0")
            port = web_server_config.get("port", 5000)

            _log.info(
                "Launching Photo Gallery web server on %s:%d (%d photos in gallery)",
                host,
                port,
                len(self._photos),
            )
            self._web_server = start_gallery_web_server(self, host, port)
        except Exception as e:
            _log.exception("Failed to start Photo Gallery web server: %s", e)

    def stop(self) -> None:
        """Stop the photo gallery module and web server."""
        _log.info("Stopping PhotoGallery module")
        if self._web_server:
            try:
                self._web_server.stop()
            except Exception as e:
                _log.exception("Failed to stop web server: %s", e)
        super().stop()

    def _setup_gallery_dir(self) -> None:
        """Create gallery directory if it doesn't exist."""
        self.gallery_dir.mkdir(exist_ok=True)
        _log.debug("Gallery directory ready at %s", self.gallery_dir.resolve())

    def _get_local_config(self) -> dict[str, Any]:
        """Load this module's own ``config.json`` file."""
        try:
            if LOCAL_CONFIG_FILE.exists():
                with open(LOCAL_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            _log.warning("Failed to load local module config: %s", e)
        return {}

    def _save_local_config(self, config: dict[str, Any]) -> None:
        """Save this module's own ``config.json`` file."""
        try:
            with open(LOCAL_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            _log.error("Failed to save local module config: %s", e)

    def _get_photo_modes(self) -> dict[str, str]:
        """Get per-photo display modes from this module's local config."""
        try:
            local_config = self._get_local_config()
            return local_config.get("photo_modes", {}) or {}
        except Exception:
            return {}

    def _save_photo_modes(self, modes: dict[str, str]) -> None:
        """Persist per-photo display modes into this module's local config."""
        try:
            local_config = self._get_local_config()
            local_config["photo_modes"] = modes
            self._save_local_config(local_config)
        except Exception as e:
            _log.error("Failed to save photo modes: %s", e)

    def _load_photos(self) -> None:
        """Load list of photo files from gallery directory."""
        with self._lock:
            # Supported image formats
            extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}
            self._photos = sorted([
                p for p in self.gallery_dir.iterdir()
                if p.is_file() and p.suffix.lower() in extensions
            ])
            _log.info(
                "Loaded %d photos from %s",
                len(self._photos),
                self.gallery_dir.resolve(),
            )
            for photo in self._photos:
                _log.debug("  - %s", photo.name)

    def _get_current_photo_path(self) -> Path | None:
        """Get the path of the current photo to display."""
        with self._lock:
            if not self._photos:
                return None
            return self._photos[self._current_photo_index]

    def _rotate_to_next_photo(self) -> None:
        """Move to the next photo in the gallery."""
        with self._lock:
            if not self._photos:
                return
            self._current_photo_index = (self._current_photo_index + 1) % len(self._photos)
            _log.debug(
                "Rotated to photo %d/%d: %s",
                self._current_photo_index + 1,
                len(self._photos),
                self._photos[self._current_photo_index].name,
            )

    def _load_and_convert_photo(self, photo_path: Path) -> Image.Image | None:
        """Load a photo and convert it to 1-bit B&W for the e-ink display."""
        try:
            # Load image
            img = Image.open(photo_path)
            original_mode = img.mode
            original_size = img.size

            # Convert to RGB if needed (handles RGBA, etc.)
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Get display mode for this photo (or use default from config)
            filename = photo_path.name
            photo_modes = self._get_photo_modes()
            display_mode = photo_modes.get(
                filename,
                self.config.get("display_mode", DEFAULT_DISPLAY_MODE),
            )
            img = self._apply_display_mode(img, display_mode)

            # Convert to 1-bit (black and white) for e-ink
            img = img.convert("1")

            _log.debug(
                "Rendered photo %s (%s %s -> %s %s, mode=%s)",
                photo_path.name,
                original_mode,
                original_size,
                img.mode,
                img.size,
                display_mode,
            )
            return img
        except Exception as e:
            _log.exception("Failed to load photo %s: %s", photo_path, e)
            return None

    def _apply_display_mode(self, img: Image.Image, mode: str) -> Image.Image:
        """Apply display mode transformations: stretched, full_screen, or bordered."""
        target_width, target_height = self.width, self.height
        img_width, img_height = img.size
        
        if mode == "stretched":
            # Stretch to fill the entire display
            return img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        elif mode == "full_screen":
            # Aspect-ratio preserving, centered
            img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
            result = Image.new("RGB", (target_width, target_height), color="white")
            x = (target_width - img.width) // 2
            y = (target_height - img.height) // 2
            result.paste(img, (x, y))
            return result
        
        elif mode == "bordered":
            # Aspect-ratio preserving with visible border
            border_size = 20
            inner_width = target_width - 2 * border_size
            inner_height = target_height - 2 * border_size
            
            img.thumbnail((inner_width, inner_height), Image.Resampling.LANCZOS)
            result = Image.new("RGB", (target_width, target_height), color="white")
            x = border_size + (inner_width - img.width) // 2
            y = border_size + (inner_height - img.height) // 2
            result.paste(img, (x, y))
            return result
        
        else:
            # Fallback to stretched
            return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    def _wake_render(self) -> None:
        """Wake the render loop without changing module view state."""
        super().on_action_button()

    def on_action_button(self) -> None:
        """Toggle between the photo gallery view and the QR code view."""
        with self._view_lock:
            self._view = "qr" if self._view == "gallery" else "gallery"
            new_view = self._view
        _log.info("Photo Gallery view -> %s", new_view)
        self._wake_render()

    def render(self) -> Image.Image:
        """Render either gallery photos or the module QR view."""
        with self._view_lock:
            view = self._view

        if view == "qr":
            qr_image = self._get_qr_image()
            if qr_image is not None:
                return qr_image
            return self._render_text_placeholder("qr.svg missing")
        return self._render_gallery_view()

    def _render_gallery_view(self) -> Image.Image:
        """Render the current photo or a placeholder if no photos exist."""
        # Check if it's time to rotate
        change_rate = self.config.get("change_rate", DEFAULT_CHANGE_RATE)
        current_time = time.time()
        if current_time - self._last_rotation_time >= change_rate:
            self._rotate_to_next_photo()
            self._last_rotation_time = current_time

        # Load and display current photo
        photo_path = self._get_current_photo_path()
        if photo_path:
            photo_image = self._load_and_convert_photo(photo_path)
            if photo_image:
                return photo_image
            _log.warning(
                "render(): failed to convert %s, falling back to placeholder",
                photo_path,
            )
        else:
            _log.info(
                "render(): no photos available in %s, showing placeholder",
                self.gallery_dir.resolve(),
            )

        return self._render_text_placeholder("No photos in gallery")

    def _render_text_placeholder(self, text: str) -> Image.Image:
        """Render a centered text placeholder."""
        placeholder = self.new_image(color=255)
        try:
            from PIL import ImageFont

            draw = ImageDraw.Draw(placeholder)
            # Try to use a default font, fall back to default if not available
            try:
                font = ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (self.width - text_width) // 2
            y = (self.height - text_height) // 2
            draw.text((x, y), text, fill=0, font=font)
        except Exception as e:
            _log.warning("Failed to render placeholder: %s", e)

        return placeholder

    def _get_qr_image(self) -> Image.Image | None:
        """Return a cached, panel-sized QR image rendered from ``qr.svg``."""
        if self._qr_image_cache is not None:
            return self._qr_image_cache
        if not QR_SVG_FILE.exists():
            _log.warning("QR file not found at %s", QR_SVG_FILE)
            return None

        try:
            svg_text = QR_SVG_FILE.read_text(encoding="utf-8")
            qr_image = self._rasterize_qr_svg(svg_text)
            self._qr_image_cache = qr_image
            return qr_image
        except Exception as e:
            _log.exception("Failed to rasterize QR SVG %s: %s", QR_SVG_FILE, e)
            return None

    def _rasterize_qr_svg(self, svg_text: str) -> Image.Image:
        """Rasterize the bundled QR SVG into a 1-bit panel-sized image."""
        canvas = self.new_image(color=255)
        draw = ImageDraw.Draw(canvas)

        rect_pattern = re.compile(r"<rect\b([^>]*)/?>", re.IGNORECASE)
        attr_pattern = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
        finder_pattern = re.compile(
            r"<svg\b[^>]*\bid=\"Ebene_1\"[^>]*\bx=\"([^\"]+)\"[^>]*\by=\"([^\"]+)\""
            r"[^>]*\bwidth=\"([^\"]+)\"[^>]*\bheight=\"([^\"]+)\"[^>]*>",
            re.IGNORECASE,
        )

        all_rects: list[tuple[float, float, float, float, str]] = []
        max_extent = 0.0

        for match in rect_pattern.finditer(svg_text):
            attrs = dict(attr_pattern.findall(match.group(1)))
            try:
                x = float(attrs.get("x", "0"))
                y = float(attrs.get("y", "0"))
                w = float(attrs.get("width", "0"))
                h = float(attrs.get("height", "0"))
            except ValueError:
                continue
            fill = attrs.get("fill", "").lower()
            all_rects.append((x, y, w, h, fill))
            max_extent = max(max_extent, x + w, y + h)

        if max_extent <= 0:
            raise ValueError("qr.svg does not contain renderable rectangles")

        target_side = max(1, min(self.width, self.height) - 20)
        offset_x = (self.width - target_side) // 2
        offset_y = (self.height - target_side) // 2
        scale = target_side / max_extent

        for x, y, w, h, fill in all_rects:
            if fill != "#000000":
                continue
            x1 = int(round(offset_x + x * scale))
            y1 = int(round(offset_y + y * scale))
            x2 = int(round(offset_x + (x + w) * scale))
            y2 = int(round(offset_y + (y + h) * scale))
            x2 = max(x2, x1 + 1)
            y2 = max(y2, y1 + 1)
            draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=0)

        # Finder patterns are present as nested SVG overlays in the attached file.
        finders: set[tuple[float, float, float, float]] = set()
        for match in finder_pattern.finditer(svg_text):
            try:
                fx = float(match.group(1))
                fy = float(match.group(2))
                fw = float(match.group(3))
                fh = float(match.group(4))
            except ValueError:
                continue
            finders.add((fx, fy, fw, fh))

        for fx, fy, fw, fh in finders:
            x1 = int(round(offset_x + fx * scale))
            y1 = int(round(offset_y + fy * scale))
            x2 = int(round(offset_x + (fx + fw) * scale))
            y2 = int(round(offset_y + (fy + fh) * scale))
            draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=0)

            inset_outer = int(round(min(fw, fh) * scale / 7))
            inset_inner = int(round((2 * min(fw, fh)) * scale / 7))

            wx1 = x1 + inset_outer
            wy1 = y1 + inset_outer
            wx2 = x2 - inset_outer
            wy2 = y2 - inset_outer
            draw.rectangle((wx1, wy1, wx2 - 1, wy2 - 1), fill=255)

            bx1 = x1 + inset_inner
            by1 = y1 + inset_inner
            bx2 = x2 - inset_inner
            by2 = y2 - inset_inner
            draw.rectangle((bx1, by1, bx2 - 1, by2 - 1), fill=0)

        return canvas

    def next_update_delay(self) -> float | None:
        """Return update interval based on change_rate config."""
        change_rate = self.config.get("change_rate", DEFAULT_CHANGE_RATE)
        return change_rate

    def add_photo(self, file_path: Path, display_mode: str | None = None) -> bool:
        """Add a photo to the gallery with optional display mode. Return True if successful."""
        try:
            # Validate that it's an image
            img = Image.open(file_path)
            img.close()

            # Copy to gallery directory
            dest_path = self.gallery_dir / file_path.name
            dest_path.write_bytes(file_path.read_bytes())

            # Store display mode if provided
            if display_mode and display_mode in ["stretched", "full_screen", "bordered"]:
                modes = self._get_photo_modes()
                modes[file_path.name] = display_mode
                self._save_photo_modes(modes)
                _log.info("Added photo: %s (display_mode=%s)", dest_path, display_mode)
            else:
                _log.info("Added photo: %s", dest_path)

            # Update photos list and force an immediate redraw
            self._load_photos()
            self._wake_render()

            return True
        except Exception as e:
            _log.exception("Failed to add photo %s: %s", file_path, e)
            return False

    def remove_photo(self, filename: str) -> bool:
        """Remove a photo from the gallery. Return True if successful."""
        try:
            photo_path = self.gallery_dir / filename
            if not (photo_path.exists() and photo_path.is_file()):
                _log.warning("remove_photo: %s does not exist", photo_path)
                return False

            photo_path.unlink()

            # Remove metadata for this photo
            modes = self._get_photo_modes()
            if filename in modes:
                del modes[filename]
                self._save_photo_modes(modes)

            # Reset index if needed
            with self._lock:
                if self._current_photo_index >= len(self._photos) - 1:
                    self._current_photo_index = 0

            self._load_photos()
            _log.info("Removed photo: %s", filename)
            self._wake_render()
            return True
        except Exception as e:
            _log.exception("Failed to remove photo %s: %s", filename, e)
            return False

    def get_photos_list(self) -> list[str]:
        """Return list of photo filenames."""
        with self._lock:
            return [p.name for p in self._photos]

    def get_photo_display_mode(self, filename: str) -> str:
        """Get the display mode for a specific photo."""
        modes = self._get_photo_modes()
        return modes.get(filename, self.config.get("display_mode", DEFAULT_DISPLAY_MODE))

    def set_photo_display_mode(self, filename: str, mode: str) -> bool:
        """Set the display mode for a specific photo."""
        if mode in ["stretched", "full_screen", "bordered"]:
            modes = self._get_photo_modes()
            modes[filename] = mode
            self._save_photo_modes(modes)
            _log.info("Set display mode for %s to %s", filename, mode)
            self._wake_render()  # Force immediate redraw
            return True
        return False

    def set_change_rate(self, seconds: int) -> None:
        """Settings are read-only and configured in config.json."""
        _log.info("Change rate setting requested: %d seconds (read-only, configure in config.json)", seconds)

    def set_display_mode(self, mode: str) -> None:
        """Settings are read-only and configured in config.json."""
        if mode in ["stretched", "full_screen", "bordered"]:
            _log.info("Display mode setting requested: %s (read-only, configure in config.json)", mode)
            self._wake_render()  # Force immediate redraw

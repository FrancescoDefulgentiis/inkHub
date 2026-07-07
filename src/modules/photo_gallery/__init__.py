"""Photo Gallery module — displays and manages a rotating gallery of photos on e-ink display."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from ...module import Module
from ...registry import register_module

_log = logging.getLogger(__name__)

# Default config
DEFAULT_CHANGE_RATE = 60  # seconds
DEFAULT_DISPLAY_MODE = "stretched"  # "full_screen", "stretched", "bordered"
GALLERY_DIR = Path("photo_gallery")
CONFIG_FILE = Path("config_files/config.json")


@register_module("photo_gallery")
class PhotoGallery(Module):
    """Display a rotating gallery of photos on the e-ink display."""

    def __init__(self, config: Mapping[str, Any], size: tuple[int, int]) -> None:
        super().__init__(config, size)
        self.gallery_dir = GALLERY_DIR
        self._setup_gallery_dir()
        
        self._current_photo_index = 0
        self._photos: list[Path] = []
        self._last_rotation_time = time.time()
        self._lock = threading.Lock()
        
        self._load_photos()
        self._web_server: Any = None

    def start(self) -> None:
        """Start the photo gallery module and web server."""
        super().start()
        
        # Start the web server if enabled
        web_server_config = self.config.get("web_server", {})
        if web_server_config.get("enabled", True):
            try:
                from .launcher import start_gallery_web_server
                
                host = web_server_config.get("host", "0.0.0.0")
                port = web_server_config.get("port", 5000)
                
                self._web_server = start_gallery_web_server(self, host, port)
                _log.info("Photo Gallery web server started on %s:%d", host, port)
            except Exception as e:
                _log.error("Failed to start Photo Gallery web server: %s", e)

    def stop(self) -> None:
        """Stop the photo gallery module and web server."""
        if self._web_server:
            try:
                self._web_server.stop()
            except Exception as e:
                _log.error("Failed to stop web server: %s", e)
        super().stop()

    def _setup_gallery_dir(self) -> None:
        """Create gallery directory if it doesn't exist."""
        self.gallery_dir.mkdir(exist_ok=True)

    def _get_global_config(self) -> dict[str, Any]:
        """Load the global config.json file."""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            _log.warning("Failed to load global config: %s", e)
        return {}

    def _save_global_config(self, config: dict[str, Any]) -> None:
        """Save the global config.json file."""
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            _log.error("Failed to save global config: %s", e)

    def _get_photo_modes(self) -> dict[str, str]:
        """Get per-photo display modes from global config."""
        try:
            global_config = self._get_global_config()
            photo_gallery_config = global_config.get("modules", {}).get("photo_gallery", {})
            return photo_gallery_config.get("photo_modes", {})
        except Exception:
            return {}

    def _save_photo_modes(self, modes: dict[str, str]) -> None:
        """Save per-photo display modes to global config."""
        try:
            global_config = self._get_global_config()
            if "modules" not in global_config:
                global_config["modules"] = {}
            if "photo_gallery" not in global_config["modules"]:
                global_config["modules"]["photo_gallery"] = {}
            
            global_config["modules"]["photo_gallery"]["photo_modes"] = modes
            self._save_global_config(global_config)
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
            _log.info("Loaded %d photos", len(self._photos))

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

    def _load_and_convert_photo(self, photo_path: Path) -> Image.Image | None:
        """Load a photo and convert it to 1-bit B&W for the e-ink display."""
        try:
            # Load image
            img = Image.open(photo_path)
            
            # Convert to RGB if needed (handles RGBA, etc.)
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            # Get display mode for this photo (or use default from config)
            filename = photo_path.name
            photo_modes = self._get_photo_modes()
            display_mode = photo_modes.get(filename, self.config.get("display_mode", DEFAULT_DISPLAY_MODE))
            img = self._apply_display_mode(img, display_mode)
            
            # Convert to 1-bit (black and white) for e-ink
            img = img.convert("1")
            
            return img
        except Exception as e:
            _log.error("Failed to load photo %s: %s", photo_path, e)
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

    def render(self) -> Image.Image:
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
        
        # Placeholder: "No photos" message
        placeholder = self.new_image(color=255)
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(placeholder)
            # Try to use a default font, fall back to default if not available
            try:
                font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()
            
            text = "No photos in gallery"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (self.width - text_width) // 2
            y = (self.height - text_height) // 2
            draw.text((x, y), text, fill=0, font=font)
        except Exception as e:
            _log.warning("Failed to render placeholder: %s", e)
        
        return placeholder

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
                _log.info("Added photo: %s with display_mode: %s", dest_path, display_mode)
            else:
                _log.info("Added photo: %s", dest_path)
            
            # Update photos list
            self._load_photos()
            
            return True
        except Exception as e:
            _log.error("Failed to add photo: %s", e)
            return False

    def remove_photo(self, filename: str) -> bool:
        """Remove a photo from the gallery. Return True if successful."""
        try:
            photo_path = self.gallery_dir / filename
            if photo_path.exists() and photo_path.is_file():
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
                return True
            return False
        except Exception as e:
            _log.error("Failed to remove photo: %s", e)
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
            self.on_action_button()  # Force immediate redraw
            return True
        return False

    def set_change_rate(self, seconds: int) -> None:
        """Settings are read-only and configured in config.json."""
        _log.info("Change rate setting requested: %d seconds (read-only, configure in config.json)", seconds)

    def set_display_mode(self, mode: str) -> None:
        """Settings are read-only and configured in config.json."""
        if mode in ["stretched", "full_screen", "bordered"]:
            _log.info("Display mode setting requested: %s (read-only, configure in config.json)", mode)
            self.on_action_button()  # Force immediate redraw

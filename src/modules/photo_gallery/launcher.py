"""Launch script for the Photo Gallery web server.

This script starts the Flask web server for the photo gallery module in a separate thread
so it doesn't block the main e-ink display application.
"""

import logging
import threading
from typing import Any

_log = logging.getLogger(__name__)


class GalleryWebServer:
    """Manages the Flask web server for the photo gallery."""

    def __init__(self, gallery: Any, host: str = "0.0.0.0", port: int = 5000) -> None:
        """Initialize the web server.

        :param gallery: The PhotoGallery module instance
        :param host: Host to bind to (0.0.0.0 for all interfaces)
        :param port: Port to bind to
        """
        self.gallery = gallery
        self.host = host
        self.port = port
        self._server_thread: threading.Thread | None = None
        self._app = None

    def start(self) -> None:
        """Start the web server in a background thread."""
        if self._server_thread and self._server_thread.is_alive():
            _log.warning("Server already running on %s:%d", self.host, self.port)
            return

        _log.info(
            "Starting Photo Gallery web server thread on %s:%d",
            self.host,
            self.port,
        )
        self._server_thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="photo-gallery-web",
        )
        self._server_thread.start()

    def _run_server(self) -> None:
        """Run the Flask server (called in background thread)."""
        try:
            _log.debug("Importing Flask app factory for photo gallery")
            from .web import create_app

            self._app = create_app(self.gallery)
            _log.info(
                "Photo Gallery web server binding to http://%s:%d",
                self.host,
                self.port,
            )
            # Use threading=False to avoid nested threading
            # use_reloader=False to prevent double initialization
            self._app.run(
                host=self.host,
                port=self.port,
                debug=False,
                use_reloader=False,
                threaded=True,
            )
            _log.info("Photo Gallery web server exited cleanly")
        except ImportError as e:
            _log.error(
                "Photo Gallery web server dependencies missing (%s). "
                "Install with: pip install flask werkzeug",
                e,
            )
        except OSError as e:
            _log.error(
                "Photo Gallery web server could not bind to %s:%d (%s). "
                "Is the port in use?",
                self.host,
                self.port,
                e,
            )
        except Exception as e:
            _log.exception("Photo Gallery web server crashed: %s", e)

    def stop(self) -> None:
        """Stop the web server."""
        # Flask doesn't provide an easy way to stop a running server in a thread.
        # The server will stop when the application exits or the thread is terminated.
        _log.info("Photo Gallery web server stop requested")


def start_gallery_web_server(
    gallery: Any,
    host: str = "0.0.0.0",
    port: int = 5000,
) -> GalleryWebServer:
    """Create and start the web server.

    :param gallery: The PhotoGallery module instance
    :param host: Host to bind to
    :param port: Port to bind to
    :return: GalleryWebServer instance
    """
    server = GalleryWebServer(gallery, host, port)
    server.start()
    return server

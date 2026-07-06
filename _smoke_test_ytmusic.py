"""Offline smoke test for the ytmusic module.

Renders the ``now_playing`` and ``queue`` views with mock data (no network,
no ytmusicapi, no hardware) and saves them as PNGs so the layout can be
eyeballed on a laptop before deploying to the Pi.

Run from the repository root:

    python _smoke_test_ytmusic.py
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

logging.basicConfig(level=logging.INFO)

# Import the module class directly (bypasses the discovery registry so we
# don't need to spin up the whole InkHubApp).
sys.path.insert(0, str(Path(__file__).parent))
from src.modules.ytmusic import (  # noqa: E402
    PlayerState,
    Track,
    YouTubeMusicModule,
    _upscale_thumb_url,
)


PANEL_SIZES = [
    ("7in5", (800, 480)),
    ("4in2", (400, 300)),
]


def _fake_cover(seed: int, size: int = 400) -> Image.Image:
    """Generate a synthetic 'album cover' — a gradient with a solid disc."""
    img = Image.new("RGB", (size, size), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for y in range(size):
        shade = int(30 + (y / size) * 200) ^ seed
        d.line([(0, y), (size, y)], fill=(shade % 256, (shade * 3) % 256, (shade * 5) % 256))
    d.ellipse(
        [size * 0.15, size * 0.15, size * 0.85, size * 0.85],
        fill=(20 + seed % 40, 20 + (seed * 2) % 40, 20 + (seed * 3) % 40),
    )
    d.ellipse(
        [size * 0.42, size * 0.42, size * 0.58, size * 0.58],
        fill=(240, 240, 240),
    )
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return Image.open(buf)


def _mock_requests_get(url, *args, **kwargs):
    """Return a fake JPEG-ish response so the module's cover loader works."""
    class FakeResp:
        def __init__(self, image: Image.Image) -> None:
            buf = io.BytesIO()
            image.save(buf, "PNG")
            self.content = buf.getvalue()

        def raise_for_status(self) -> None:
            pass

    seed = abs(hash(url)) % 256
    img = _fake_cover(seed=seed, size=400)
    return FakeResp(img)


def _mock_state() -> PlayerState:
    from datetime import datetime

    def _mk(vid: str, title: str, artist: str, album: str, duration: str) -> Track:
        return Track(
            video_id=vid,
            title=title,
            artists=artist,
            album=album,
            duration=duration,
            duration_seconds=200,
            thumbnail_url=f"https://lh3.googleusercontent.com/{vid}=w60-h60-l90-rj",
            is_explicit=False,
        )

    return PlayerState(
        current=_mk(
            "abc123",
            "The Nights of My Life (feat. Long Guest Artist)",
            "Avicii, David Guetta",
            "Stories (Deluxe Edition Remastered 2023)",
            "3:52",
        ),
        queue=[
            _mk("v1", "Wake Me Up", "Avicii", "True", "4:09"),
            _mk("v2", "Hey Brother", "Avicii", "True", "4:15"),
            _mk("v3", "Levels (Original Version)", "Avicii", "Levels", "5:37"),
            _mk("v4", "Waiting For Love", "Avicii", "Stories", "3:51"),
            _mk("v5", "Without You (feat. Sandro Cavazza)", "Avicii", "Avīci (01)", "2:56"),
        ],
        fetched_at=datetime.now(),
        error=None,
    )


def render_all() -> None:
    out_dir = Path(__file__).parent / "smoke_output"
    out_dir.mkdir(exist_ok=True)

    with patch("src.modules.ytmusic.requests.get", side_effect=_mock_requests_get):
        for label, size in PANEL_SIZES:
            module = YouTubeMusicModule(
                config={
                    "auth_file": "browser.json",
                    "poll_interval": 5,
                    "default_view": "now_playing",
                    "queue_size": 5,
                },
                size=size,
            )
            # Inject mock state so render() has data.
            module._state = _mock_state()
            module._last_pushed_key = None

            # Render Now Playing
            module._view = "now_playing"
            img_np = module.render()
            path_np = out_dir / f"ytmusic_now_playing_{label}.png"
            img_np.save(path_np)
            print(f"Wrote {path_np}")

            # Render Queue
            module._view = "queue"
            img_q = module.render()
            path_q = out_dir / f"ytmusic_queue_{label}.png"
            img_q.save(path_q)
            print(f"Wrote {path_q}")

            # Render "waiting for data" placeholder
            module._state = PlayerState(error=None)
            img_wait = module.render()
            path_wait = out_dir / f"ytmusic_waiting_{label}.png"
            img_wait.save(path_wait)
            print(f"Wrote {path_wait}")


def test_upscale_urls() -> None:
    """Quick unit-style check for the thumbnail-URL upscaler."""
    cases = [
        (
            "https://lh3.googleusercontent.com/abc=w60-h60-l90-rj",
            400,
            "https://lh3.googleusercontent.com/abc=w400-h400-l90-rj",
        ),
        (
            "https://lh3.googleusercontent.com/xyz=s120",
            300,
            "https://lh3.googleusercontent.com/xyz=s300",
        ),
        (
            "https://example.com/no-size-params.jpg",
            500,
            "https://example.com/no-size-params.jpg",
        ),
    ]
    for input_url, side, expected in cases:
        got = _upscale_thumb_url(input_url, side)
        assert got == expected, f"upscale({input_url!r}, {side}) = {got!r}, expected {expected!r}"
    print("upscale URL tests passed")


if __name__ == "__main__":
    test_upscale_urls()
    render_all()
    print("\nSmoke test complete. Open PNGs in ./smoke_output/ to eyeball layout.")

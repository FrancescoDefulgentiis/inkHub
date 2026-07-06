# YouTube Music module — credentials folder

The `ytmusic` module reads its authentication credentials from this folder.

By default it looks for `browser.json` here (i.e.
`src/modules/ytmusic/browser.json`). The `.gitignore` in this folder makes
sure the credentials never accidentally end up in git.

## Generate `browser.json`

1. On any desktop, open Chromium or Firefox and log in to
   <https://music.youtube.com>.
2. Open DevTools (F12) → **Network** tab → play a song.
3. Find any authenticated POST request to `music.youtube.com/youtubei/v1/browse`.
4. Right-click it → **Copy → Copy as cURL** (Chromium) or **Copy → Copy
   request headers** (Firefox).
5. From a terminal, run:

   ```bash
   ytmusicapi browser
   ```

   Paste the copied content when prompted. A `browser.json` file is written
   to your current directory.
6. Move that `browser.json` into **this folder** (`src/modules/ytmusic/`).

## Point the module elsewhere (optional)

The path is configurable in `config.json`:

```json
"ytmusic": {
    "auth_file": "src/modules/ytmusic/browser.json"
}
```

Relative paths are resolved from the InkHub working directory (i.e. the
repository root, where you run `python -m src`). Absolute paths work too if
you'd rather keep the file elsewhere on disk.

## Security

The `browser.json` file contains cookies and an `Authorization` header that
are equivalent to your live YouTube Music session. **Treat it like a
password.** If you ever paste its contents somewhere public, log out of
YouTube on the source browser to invalidate the session.

# Photo Gallery Module Setup Guide

A complete step-by-step guide to set up and run the Photo Gallery module on your InkHub e-ink dashboard.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Starting the Web Server](#starting-the-web-server)
5. [Accessing the Web Interface](#accessing-the-web-interface)
6. [Using the Web Interface](#using-the-web-interface)
7. [Managing Display Settings](#managing-display-settings)
8. [Running in Production](#running-in-production)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Raspberry Pi** (or any Linux machine running InkHub)
- **Python 3.8+** installed
- **512 MB RAM minimum** (tested and optimized)
- **Network connectivity** (WiFi or Ethernet)
- **Web browser** on another machine to access the interface

## Installation

### Step 1: Verify Dependencies are Installed

The Photo Gallery module requires Flask for the web interface. Check that it's in your requirements:

```bash
cd /path/to/inkHub
cat requirements.txt | grep -i flask
```

If Flask is not listed, install it:

```bash
pip install Flask>=2.0
```

### Step 2: Verify Module Structure

The Photo Gallery module should be organized as follows:

```
src/modules/photo_gallery/
├── __init__.py           # Core PhotoGallery class
├── web.py               # Flask web server
├── launcher.py          # Web server launcher
├── qr.svg               # QR code shown by the action-button alternate view
└── SETUP.md             # This file
```

If files are missing or misplaced, restore them from the repository.

### Action Button Behavior

When the Photo Gallery module is active, pressing the dedicated action button toggles between:

- **Gallery view** (normal rotating photos)
- **QR view** (renders `src/modules/photo_gallery/qr.svg`)

### Step 3: Create the Gallery Directory

The module automatically creates a `photo_gallery/` directory in the project root when first run. This directory will store all uploaded photos:

```
project_root/
└── photo_gallery/
    ├── photo1.jpg
    ├── photo2.png
    └── photo3.bmp
```

You can create this manually if you prefer:

```bash
mkdir -p photo_gallery
```

---

## Configuration

### Step 1: Open the Configuration File

Edit the main InkHub configuration file:

```bash
nano config_files/config.json
```

### Step 2: Configure Photo Gallery Settings

Locate the `"photo_gallery"` section and verify these settings:

```json
{
  "modules": {
    "photo_gallery": {
      "change_rate": 60,
      "display_mode": "bordered",
      "web_server": {
        "enabled": true,
        "host": "0.0.0.0",
        "port": 5000
      }
    }
  }
}
```

#### Configuration Options

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `change_rate` | integer (seconds) | 60 | How often to rotate to the next photo on the e-ink display |
| `display_mode` | string | "bordered" | How to display photos: `"stretched"`, `"full_screen"`, or `"bordered"` |
| `web_server.enabled` | boolean | true | Whether to start the web server |
| `web_server.host` | string | "0.0.0.0" | Listen address (0.0.0.0 = all interfaces) |
| `web_server.port` | integer | 5000 | Port to run the web server on |

#### Display Mode Details

- **`"stretched"`**: Resize photo to fill entire display (may distort aspect ratio)
- **`"full_screen"`**: Keep aspect ratio, center in white space (letterboxing)
- **`"bordered"`**: Keep aspect ratio with 20px white border around photo

### Step 3: Save Configuration

Save the file and verify no JSON syntax errors:

```bash
python -c "import json; json.load(open('config_files/config.json'))"
```

If no output, the JSON is valid. If you see an error, fix the syntax and try again.

---

## Starting the Web Server

### Important: The Web Server Runs Independently

The Photo Gallery web server runs as a **background daemon thread** and operates **independently** from which module is currently displayed on the e-ink panel. This means:

✅ You can upload/manage photos while the **clock** is displayed
✅ You can upload/manage photos while the **weather** is displayed  
✅ You can upload/manage photos while **any other module** is displayed

The web server stays running until you stop InkHub.

### Step 1: Start InkHub

Run the main InkHub application normally:

```bash
python run.py
```

Or with no terminal menu:

```bash
python run.py --no-menu
```

### Step 2: Verify Web Server Started

Check the logs for this message:

```
Photo Gallery web server started on 0.0.0.0:5000
```

If you see this, the server is running and ready to accept connections.

### Step 3: Keep the Server Running

The web server runs as long as the InkHub application is running. To keep it running permanently on a Raspberry Pi:

#### Option A: Run with systemd (Recommended for Production)

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/inkhub.service
```

Add this content:

```ini
[Unit]
Description=InkHub E-Ink Dashboard
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/inkHub
ExecStart=/usr/bin/python3 run.py --no-menu
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable inkhub.service
sudo systemctl start inkhub.service
```

Check status:

```bash
sudo systemctl status inkhub.service
```

#### Option B: Run with nohup (Quick Test)

```bash
nohup python run.py --no-menu > inkhub.log 2>&1 &
```

Then access the web server while the process runs.

#### Option C: Run in Screen Session (Development)

```bash
screen -S inkhub -d -m python run.py --no-menu
```

Reattach to the session:

```bash
screen -r inkhub
```

---

## Accessing the Web Interface

### Step 1: Find Your Raspberry Pi's IP Address

On the Raspberry Pi:

```bash
hostname -I
```

Output example: `192.168.1.69`

### Step 2: Open Web Browser on Another Machine

On your computer or phone, open a web browser and navigate to:

```
http://192.168.1.69:5000
```

Replace `192.168.1.69` with your Pi's actual IP address.

### Step 3: Verify Access

You should see the Photo Gallery Manager interface with these sections:
- Upload area
- Current gallery photos
- Settings panel

If you get a connection error:
- Check the Pi is powered on and connected to network
- Verify the port is 5000 (check config.json)
- Check firewall isn't blocking port 5000
- See [Troubleshooting](#troubleshooting) section

---

## Using the Web Interface

### Uploading Photos

1. **Drag and Drop**: Drag image files onto the upload area
2. **Click to Browse**: Click the upload area to open file browser
3. **Select Display Mode**: Choose how you want **THIS PHOTO** displayed:
   - `stretched` - Fill the entire screen
   - `full_screen` - Keep aspect ratio with white borders
   - `bordered` - Keep aspect ratio with extra 20px border
4. **Upload**: Click upload button or complete drag-and-drop

Each photo can have its own display mode! One photo can be stretched while another is bordered.

### Supported Photo Formats

- **JPEG** (.jpg, .jpeg)
- **PNG** (.png)
- **BMP** (.bmp)
- **GIF** (.gif)

Maximum file size: **10 MB**

### Managing Your Photos

#### View Photos

The gallery section displays all uploaded photos as thumbnails. Scroll to see all photos.

#### Delete Photos

- Click the **trash icon** on any photo thumbnail
- Confirm deletion when prompted
- Photo is permanently removed from the gallery

#### Change Photo Display Mode

Each photo shows its current display mode. To change it:

1. Click on the photo or its settings
2. Select new display mode: `stretched` / `full_screen` / `bordered`
3. Changes apply immediately

### Adjusting Rotation Speed

The **Change Rate** determines how often the e-ink display advances to the next photo. To change it:

1. Edit `config_files/config.json`
2. Update the `"change_rate"` value (in seconds)
3. Restart InkHub

Examples:
- `30` = Change photo every 30 seconds (fast rotation)
- `60` = Change photo every 60 seconds (default)
- `300` = Change photo every 5 minutes (slow rotation)

---

## Managing Display Settings

### Per-Photo Display Modes

Each photo in your gallery can have its own display mode. When uploading, you select the display mode for that specific photo.

To change a photo's display mode after upload:
1. Open http://192.168.1.69:5000
2. Find the photo in the gallery
3. Click on it to see options (display mode selector)
4. Select new mode: `stretched` / `full_screen` / `bordered`
5. Changes apply immediately

### Default Display Mode

If you don't specify a display mode when uploading, the default from `config.json` is used:

```json
"photo_gallery": {
  "display_mode": "bordered"
}
```

Edit this in `config_files/config.json` and restart InkHub to change the default for all new uploads.

---

## Running in Production

### Memory Usage

The Photo Gallery module is optimized for **512 MB RAM** Raspberry Pi:

- **Module overhead**: ~10-15 MB
- **Web server**: ~20-30 MB  
- **Per-photo cache**: ~1-2 MB
- **Total typical usage**: 50-70 MB

This leaves plenty of room for other system processes.

### Disk Space

Photos are stored in the `photo_gallery/` directory. Plan disk space accordingly:

- Each photo size varies by resolution and compression
- JPEG files are typically 30-300 KB per photo
- High-resolution photos: up to 5-10 MB each

Monitor available space:

```bash
df -h /path/to/photo_gallery
```

### Network Considerations

- **Local Network Only**: The web server is accessible only on your local network
- **For Remote Access**: Set up port forwarding on your router (security risk) or use a VPN
- **Firewall**: Ensure port 5000 is not blocked by router or local firewall

### Background Operation

The web server continues running even when:
- Different modules are active on the e-ink display
- No one is accessing the web interface
- The device is idle

This is by design. To stop it, simply stop the InkHub application.

---

## Troubleshooting

### Web Server Won't Start

**Problem**: See error `"Failed to start web server"` in logs

**Solutions**:
1. Check port 5000 is not in use:
   ```bash
   lsof -i :5000
   ```
   Kill any process using it, or change port in config.json

2. Check file permissions:
   ```bash
   ls -la photo_gallery/
   ```
   The directory should be readable/writable by the user running InkHub

3. Check Flask is installed:
   ```bash
   python -c "import flask; print(flask.__version__)"
   ```

### Can't Access Web Interface

**Problem**: Browser shows "Connection refused" or "Connection timeout"

**Solutions**:
1. Verify server is running - check logs for "Photo Gallery web server started"
2. Check IP address is correct:
   ```bash
   hostname -I
   ```
3. Check port in URL matches config.json (default 5000)
4. Ensure both machines are on same network (ping test):
   ```bash
   ping 192.168.1.69
   ```
5. Check firewall isn't blocking port 5000

### Photo Upload Fails

**Problem**: Upload button doesn't work or shows error

**Solutions**:
1. Check file size is under 10 MB
2. Check file format is supported (JPEG, PNG, BMP, GIF)
3. Check disk space is available:
   ```bash
   df -h
   ```
4. Check write permissions on photo_gallery/:
   ```bash
   touch photo_gallery/test && rm photo_gallery/test
   ```

### Settings Not Saving

**Problem**: Change Rate or Display Mode doesn't persist after restart

**Solutions**:
1. Verify settings are in `config.json`:
   ```bash
   cat config_files/config.json | grep -A 10 "photo_gallery"
   ```
2. Check that `modules.photo_gallery` section exists
3. Manually add if missing (see Configuration section)

### Photos Display But Don't Rotate

**Problem**: E-ink display shows a photo but doesn't advance

**Solutions**:
1. Verify Change Rate setting is reasonable (> 0 seconds)
2. Check photo_gallery is the active module (not clock, weather, etc.)
3. Restart InkHub to refresh module state
4. Check logs for any errors

### Memory Issues on Raspberry Pi

**Problem**: System becomes slow or unresponsive

**Solutions**:
1. Delete unused photos to free RAM
2. Reduce Change Rate to process photos less frequently
3. Reduce photo quality/resolution before uploading
4. Check what else is running:
   ```bash
   top
   ```

### Photos Show as Black/Corrupt

**Problem**: Photos display incorrectly on e-ink screen

**Solutions**:
1. Verify uploaded image file is not corrupt (open on computer)
2. Try different Display Mode in settings
3. Try uploading different image format (JPEG vs PNG)
4. Check image dimensions aren't unusual

### Web Server Crashes

**Problem**: Server was running, then suddenly stopped

**Solutions**:
1. Check logs for errors:
   ```bash
   tail -f inkhub.log
   ```
2. Restart InkHub
3. If systemd service is used, check service logs:
   ```bash
   sudo journalctl -u inkhub.service -n 50
   ```
4. Increase log level for debugging:
   ```json
   "log_level": "DEBUG"
   ```

---

## Quick Reference

### Start InkHub with Photo Gallery
```bash
python run.py
```

### Access Web Interface
```
http://<pi-ip>:5000
```

### Check If Server is Running
```bash
curl http://localhost:5000
```

### View Uploaded Photos
```bash
ls -la photo_gallery/
```

### View Current Settings
```bash
cat config_files/config.json
```

### Stop InkHub
```
Ctrl+C in the terminal where it's running
```

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review InkHub logs: `journalctl -u inkhub.service` (if using systemd)
3. Check individual module logs for detailed error messages

---

**Last Updated**: 2025  
**Version**: 1.0  
**Module**: Photo Gallery  
**Compatible**: InkHub 1.0+

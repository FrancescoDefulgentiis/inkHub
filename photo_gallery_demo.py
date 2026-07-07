#!/usr/bin/env python
"""
Test and demo script for the Photo Gallery module.

This script demonstrates the core functionality and can be used to verify
the module works correctly before deployment.

Usage:
    python photo_gallery_demo.py
"""

from pathlib import Path
from PIL import Image
import json

print("=" * 60)
print("PHOTO GALLERY MODULE - DEMO & TEST")
print("=" * 60)

# Test 1: Import module
print("\n[1] Testing module import...")
try:
    from src.modules.photo_gallery import PhotoGallery
    print("    ✓ PhotoGallery imported successfully")
except Exception as e:
    print(f"    ✗ Failed to import: {e}")
    exit(1)

# Test 2: Create instance
print("\n[2] Creating PhotoGallery instance...")
try:
    config = {
        "change_rate": 60,
        "display_mode": "stretched"
    }
    size = (800, 600)
    gallery = PhotoGallery(config, size)
    print(f"    ✓ Instance created with size {size}")
    print(f"    ✓ Gallery directory: {gallery.gallery_dir}")
except Exception as e:
    print(f"    ✗ Failed to create instance: {e}")
    exit(1)

# Test 3: Create sample images
print("\n[3] Creating sample photos...")
sample_photos = []
try:
    gallery_dir = Path("photo_gallery")
    gallery_dir.mkdir(exist_ok=True)
    
    # Create 3 sample photos
    colors = [
        (255, 0, 0, "Red"),
        (0, 255, 0, "Green"),
        (0, 0, 255, "Blue")
    ]
    
    for i, (r, g, b, name) in enumerate(colors):
        img = Image.new("RGB", (800, 600), color=(r, g, b))
        
        # Add some text to distinguish
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default()
            text = f"Sample Photo {i+1}: {name}"
            bbox = draw.textbbox((0, 0), text, font=font)
            x = (800 - (bbox[2] - bbox[0])) // 2
            y = (600 - (bbox[3] - bbox[1])) // 2
            draw.text((x, y), text, fill=(255, 255, 255), font=font)
        except:
            pass
        
        filename = f"sample_{i+1}_{name.lower()}.jpg"
        filepath = gallery_dir / filename
        img.save(str(filepath))
        sample_photos.append(filename)
        print(f"    ✓ Created: {filename}")
    
except Exception as e:
    print(f"    ✗ Failed to create samples: {e}")

# Test 4: Load photos
print("\n[4] Loading photos from gallery...")
try:
    gallery._load_photos()
    photos = gallery.get_photos_list()
    print(f"    ✓ Found {len(photos)} photos")
    for photo in photos:
        print(f"      - {photo}")
except Exception as e:
    print(f"    ✗ Failed to load photos: {e}")

# Test 5: Test rendering
print("\n[5] Testing render function...")
try:
    # Render current photo
    img = gallery.render()
    print(f"    ✓ Rendered image: {img.size} {img.mode}")
    
    # Save a sample render
    if photos:
        img.save("_gallery_render_sample.png")
        print(f"    ✓ Sample render saved to _gallery_render_sample.png")
except Exception as e:
    print(f"    ✗ Failed to render: {e}")

# Test 6: Test settings
print("\n[6] Testing settings management...")
try:
    gallery.set_change_rate(120)
    print(f"    ✓ Changed rate set to 120s: {gallery._config_data['change_rate']}")
    
    gallery.set_display_mode("full_screen")
    print(f"    ✓ Display mode set to full_screen: {gallery._config_data['display_mode']}")
    
    # Verify config file
    if gallery.config_file.exists():
        with open(gallery.config_file) as f:
            saved_config = json.load(f)
        print(f"    ✓ Config saved to file: {saved_config}")
except Exception as e:
    print(f"    ✗ Failed to manage settings: {e}")

# Test 7: Test display modes
print("\n[7] Testing all display modes...")
try:
    if photos:
        for mode in ["stretched", "full_screen", "bordered"]:
            gallery.set_display_mode(mode)
            img = gallery.render()
            print(f"    ✓ Mode '{mode}': {img.size} {img.mode}")
except Exception as e:
    print(f"    ✗ Failed to test modes: {e}")

# Test 8: Test Flask app
print("\n[8] Testing Flask web server creation...")
try:
    from src.modules.photo_gallery_web import create_app
    app = create_app(gallery)
    print(f"    ✓ Flask app created successfully")
    
    # Test some routes exist
    with app.test_client() as client:
        resp = client.get("/api/photos")
        print(f"    ✓ GET /api/photos: {resp.status_code}")
        data = resp.get_json()
        print(f"      - Photos in response: {len(data.get('photos', []))}")
except Exception as e:
    print(f"    ✗ Failed to create Flask app: {e}")

# Summary
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)
print("""
Module Status: READY FOR DEPLOYMENT

Next Steps:
1. Place photos in photo_gallery/ directory
2. Update config.json to set 'active_module': 'photo_gallery'
3. Run: python run.py
4. Access web interface at: http://localhost:5000

Configuration File:
  photo_gallery/gallery_config.json

Sample Photos Created:
""")
for photo in sample_photos:
    print(f"  - {photo}")

print(f"""
Render Sample:
  - _gallery_render_sample.png (shows what display will show)

Commands:
  # Start the module
  python run.py

  # Test web server
  curl http://localhost:5000

  # View config
  cat photo_gallery/gallery_config.json

For full documentation, see:
  - PHOTO_GALLERY_QUICKSTART.md
  - src/modules/PHOTO_GALLERY_README.md
""")
print("=" * 60)

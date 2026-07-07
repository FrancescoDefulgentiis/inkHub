"""Flask web server for Photo Gallery module management.

This provides a lightweight web interface for uploading, viewing, and managing
photos in the gallery. Designed to run on Raspberry Pi with minimal RAM usage.

Usage:
    from .web import create_app
    app = create_app(photo_gallery_module)
    app.run(host="0.0.0.0", port=5000)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from flask import Flask, render_template_string, request, jsonify, send_file
from werkzeug.utils import secure_filename

if TYPE_CHECKING:
    from . import PhotoGallery

_log = logging.getLogger(__name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "gif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def create_app(gallery: PhotoGallery) -> Flask:
    """Create and configure the Flask app for gallery management."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
    app.config["UPLOAD_FOLDER"] = str(gallery.gallery_dir)

    # HTML Template
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Photo Gallery Manager</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                background: white;
                border-radius: 8px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px 20px;
                text-align: center;
            }
            .header h1 {
                font-size: 2em;
                margin-bottom: 10px;
            }
            .header p {
                opacity: 0.9;
                font-size: 0.95em;
            }
            .content {
                padding: 30px;
            }
            .section {
                margin-bottom: 30px;
            }
            .section h2 {
                font-size: 1.3em;
                margin-bottom: 15px;
                color: #333;
                border-bottom: 2px solid #667eea;
                padding-bottom: 10px;
            }
            .upload-area {
                border: 2px dashed #667eea;
                border-radius: 8px;
                padding: 40px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s;
                background: #f8f9fa;
            }
            .upload-area:hover {
                background: #e9ecef;
                border-color: #764ba2;
            }
            .upload-area.dragover {
                background: #e3f2fd;
                border-color: #667eea;
            }
            .upload-area input[type="file"] {
                display: none;
            }
            .upload-icon {
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .upload-text {
                font-size: 1.1em;
                color: #667eea;
                margin-bottom: 5px;
                font-weight: 600;
            }
            .upload-hint {
                font-size: 0.9em;
                color: #666;
            }
            .controls {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-bottom: 20px;
            }
            .control-group {
                display: flex;
                flex-direction: column;
            }
            .control-group label {
                font-weight: 600;
                margin-bottom: 8px;
                color: #333;
            }
            .control-group select,
            .control-group input {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 1em;
                transition: border-color 0.3s;
            }
            .control-group select:focus,
            .control-group input:focus {
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }
            .button-group {
                display: flex;
                gap: 10px;
                margin-top: 15px;
            }
            button {
                flex: 1;
                padding: 12px 24px;
                border: none;
                border-radius: 4px;
                font-size: 1em;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
            }
            .btn-primary {
                background: #667eea;
                color: white;
            }
            .btn-primary:hover {
                background: #5568d3;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .btn-danger {
                background: #f56565;
                color: white;
            }
            .btn-danger:hover {
                background: #e53e3e;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(245, 101, 101, 0.4);
            }
            .btn-secondary {
                background: #cbd5e0;
                color: #333;
            }
            .btn-secondary:hover {
                background: #a0aec0;
            }
            .gallery-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
                gap: 15px;
            }
            .photo-item {
                position: relative;
                border-radius: 4px;
                overflow: hidden;
                background: #f0f0f0;
                aspect-ratio: 1;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                transition: transform 0.3s;
            }
            .photo-item:hover {
                transform: scale(1.05);
            }
            .photo-item img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }
            .photo-item .delete-btn {
                position: absolute;
                top: 5px;
                right: 5px;
                background: #f56565;
                color: white;
                border: none;
                border-radius: 50%;
                width: 28px;
                height: 28px;
                cursor: pointer;
                font-size: 0.8em;
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0;
                transition: opacity 0.3s;
            }
            .photo-item:hover .delete-btn {
                opacity: 1;
            }
            .photo-item .delete-btn:hover {
                background: #e53e3e;
            }
            .empty-message {
                text-align: center;
                padding: 40px;
                color: #999;
                font-style: italic;
            }
            .alert {
                padding: 15px;
                border-radius: 4px;
                margin-bottom: 20px;
                display: none;
            }
            .alert.show {
                display: block;
            }
            .alert-success {
                background: #c6f6d5;
                color: #22543d;
                border-left: 4px solid #48bb78;
            }
            .alert-error {
                background: #fed7d7;
                color: #742a2a;
                border-left: 4px solid #f56565;
            }
            .spinner {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 3px solid rgba(255, 255, 255, 0.3);
                border-top: 3px solid white;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
                margin-bottom: 20px;
            }
            .stat-box {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 4px;
                border-left: 4px solid #667eea;
            }
            .stat-label {
                font-size: 0.9em;
                color: #666;
                margin-bottom: 5px;
            }
            .stat-value {
                font-size: 1.8em;
                font-weight: 700;
                color: #667eea;
            }
            .progress-bar {
                width: 100%;
                height: 4px;
                background: #e2e8f0;
                border-radius: 2px;
                overflow: hidden;
                margin-top: 10px;
            }
            .progress-fill {
                height: 100%;
                background: #667eea;
                width: 0%;
                transition: width 0.3s;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Photo Gallery Manager</h1>
                <p>Upload and manage photos for your e-ink display</p>
            </div>

            <div class="content">
                <div id="alert" class="alert"></div>

                <!-- Upload Section -->
                <div class="section">
                    <h2>Upload Photo</h2>
                    <div class="upload-area" id="uploadArea">
                        <div class="upload-icon">+</div>
                        <div class="upload-text">Click to upload or drag and drop</div>
                        <div class="upload-hint">JPG, PNG, BMP, or GIF (max 10 MB)</div>
                        <input type="file" id="fileInput" accept=".jpg,.jpeg,.png,.bmp,.gif">
                    </div>
                    <div class="progress-bar" id="progressBar" style="display: none;">
                        <div class="progress-fill" id="progressFill"></div>
                    </div>
                </div>

                <!-- Settings Section -->
                <div class="section">
                    <h2>Settings</h2>
                    <div class="stats">
                        <div class="stat-box">
                            <div class="stat-label">Photos in Gallery</div>
                            <div class="stat-value" id="photoCount">0</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Current Mode</div>
                            <div class="stat-value" id="currentMode" style="font-size: 1em;">-</div>
                        </div>
                    </div>

                    <div class="controls">
                        <div class="control-group">
                            <label for="displayMode">Display Mode</label>
                            <select id="displayMode">
                                <option value="stretched">Stretched (fills entire screen)</option>
                                <option value="full_screen">Full Screen (aspect ratio preserved)</option>
                                <option value="bordered">Bordered (with white border)</option>
                            </select>
                        </div>
                        <div class="control-group">
                            <label for="changeRate">Photo Change Rate (seconds)</label>
                            <input type="number" id="changeRate" min="5" max="3600" value="60">
                        </div>
                    </div>

                    <div class="button-group">
                        <button class="btn-primary" id="savSettingsBtn">Save Settings</button>
                    </div>
                </div>

                <!-- Gallery Section -->
                <div class="section">
                    <h2>Current Gallery</h2>
                    <div class="gallery-grid" id="galleryGrid"></div>
                    <div class="empty-message" id="emptyMessage" style="display: none;">
                        No photos yet. Upload your first photo above!
                    </div>
                </div>
            </div>
        </div>

        <script>
            const uploadArea = document.getElementById('uploadArea');
            const fileInput = document.getElementById('fileInput');
            const galleryGrid = document.getElementById('galleryGrid');
            const emptyMessage = document.getElementById('emptyMessage');
            const photoCountEl = document.getElementById('photoCount');
            const currentModeEl = document.getElementById('currentMode');
            const displayModeSelect = document.getElementById('displayMode');
            const changeRateInput = document.getElementById('changeRate');
            const saveSettingsBtn = document.getElementById('savSettingsBtn');
            const progressBar = document.getElementById('progressBar');
            const progressFill = document.getElementById('progressFill');
            const alertDiv = document.getElementById('alert');

            // Upload area drag and drop
            uploadArea.addEventListener('click', () => fileInput.click());
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });
            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });
            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length) {
                    handleFileUpload(files[0]);
                }
            });

            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length) {
                    handleFileUpload(e.target.files[0]);
                }
            });

            function showAlert(message, type) {
                alertDiv.textContent = message;
                alertDiv.className = `alert show alert-${type}`;
                setTimeout(() => alertDiv.classList.remove('show'), 5000);
            }

            function handleFileUpload(file) {
                if (!['image/jpeg', 'image/png', 'image/bmp', 'image/gif'].includes(file.type)) {
                    showAlert('Invalid file type. Please upload JPG, PNG, BMP, or GIF.', 'error');
                    return;
                }

                const formData = new FormData();
                formData.append('file', file);
                formData.append('display_mode', displayModeSelect.value);

                progressBar.style.display = 'block';
                progressFill.style.width = '0%';

                const xhr = new XMLHttpRequest();
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const percentComplete = (e.loaded / e.total) * 100;
                        progressFill.style.width = percentComplete + '%';
                    }
                });

                xhr.addEventListener('load', () => {
                    progressBar.style.display = 'none';
                    if (xhr.status === 200) {
                        showAlert('Photo uploaded successfully!', 'success');
                        fileInput.value = '';
                        loadGallery();
                    } else {
                        const response = JSON.parse(xhr.responseText);
                        showAlert(`Upload failed: ${response.error}`, 'error');
                    }
                });

                xhr.addEventListener('error', () => {
                    progressBar.style.display = 'none';
                    showAlert('Upload failed. Please try again.', 'error');
                });

                xhr.open('POST', '/upload');
                xhr.send(formData);
            }

            function loadGallery() {
                fetch('/api/photos')
                    .then(r => r.json())
                    .then(data => {
                        photoCountEl.textContent = data.photos.length;
                        currentModeEl.textContent = data.display_mode || '-';
                        displayModeSelect.value = data.display_mode || 'stretched';
                        changeRateInput.value = data.change_rate || 60;

                        if (data.photos.length === 0) {
                            galleryGrid.innerHTML = '';
                            emptyMessage.style.display = 'block';
                        } else {
                            emptyMessage.style.display = 'none';
                            galleryGrid.innerHTML = data.photos.map(photo => `
                                <div class="photo-item">
                                    <img src="/photo/${encodeURIComponent(photo)}" alt="${photo}">
                                    <button class="delete-btn" onclick="deletePhoto('${photo}')">X</button>
                                </div>
                            `).join('');
                        }
                    })
                    .catch(err => {
                        console.error('Failed to load gallery:', err);
                        showAlert('Failed to load gallery', 'error');
                    });
            }

            function deletePhoto(filename) {
                if (!confirm(`Delete "${filename}"?`)) return;

                fetch(`/api/photos/${encodeURIComponent(filename)}`, { method: 'DELETE' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            showAlert('Photo deleted', 'success');
                            loadGallery();
                        } else {
                            showAlert(`Delete failed: ${data.error}`, 'error');
                        }
                    })
                    .catch(err => {
                        console.error('Delete failed:', err);
                        showAlert('Failed to delete photo', 'error');
                    });
            }

            saveSettingsBtn.addEventListener('click', () => {
                const display_mode = displayModeSelect.value;
                const change_rate = parseInt(changeRateInput.value);

                if (change_rate < 5 || change_rate > 3600) {
                    showAlert('Change rate must be between 5 and 3600 seconds', 'error');
                    return;
                }

                fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ display_mode, change_rate })
                })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            showAlert('Settings saved successfully!', 'success');
                            loadGallery();
                        } else {
                            showAlert(`Save failed: ${data.error}`, 'error');
                        }
                    })
                    .catch(err => {
                        console.error('Settings save failed:', err);
                        showAlert('Failed to save settings', 'error');
                    });
            });

            // Load gallery on page load
            loadGallery();
            setInterval(loadGallery, 5000); // Refresh every 5 seconds
        </script>
    </body>
    </html>
    """

    @app.route("/")
    def index():
        """Render the main gallery management page."""
        return render_template_string(HTML_TEMPLATE)

    @app.route("/upload", methods=["POST"])
    def upload_file():
        """Handle photo upload."""
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        try:
            filename = secure_filename(file.filename)
            filepath = Path(app.config["UPLOAD_FOLDER"]) / filename
            file.save(str(filepath))

            # Add to gallery module
            display_mode = request.form.get("display_mode")
            gallery.add_photo(filepath, display_mode)

            return jsonify({"success": True}), 200
        except Exception as e:
            _log.error("Upload failed: %s", e)
            return jsonify({"error": "Upload failed"}), 500

    @app.route("/photo/<filename>")
    def get_photo(filename):
        """Serve a photo thumbnail for preview."""
        try:
            filename = secure_filename(filename)
            filepath = Path(app.config["UPLOAD_FOLDER"]) / filename

            if not filepath.exists():
                return "File not found", 404

            return send_file(str(filepath), mimetype="image/jpeg")
        except Exception as e:
            _log.error("Failed to serve photo: %s", e)
            return "Error serving photo", 500

    @app.route("/api/photos", methods=["GET"])
    def list_photos():
        """Get list of photos and current settings."""
        try:
            photos = gallery.get_photos_list()
            return jsonify({
                "photos": photos,
                "display_mode": gallery._config_data.get("display_mode", "stretched"),
                "change_rate": gallery._config_data.get("change_rate", 60),
            }), 200
        except Exception as e:
            _log.error("Failed to list photos: %s", e)
            return jsonify({"error": "Failed to list photos"}), 500

    @app.route("/api/photos/<filename>", methods=["DELETE"])
    def delete_photo(filename):
        """Delete a photo from the gallery."""
        try:
            filename = secure_filename(filename)
            success = gallery.remove_photo(filename)
            if success:
                return jsonify({"success": True}), 200
            else:
                return jsonify({"error": "Photo not found"}), 404
        except Exception as e:
            _log.error("Failed to delete photo: %s", e)
            return jsonify({"error": "Delete failed"}), 500

    @app.route("/api/settings", methods=["POST"])
    def update_settings():
        """Update gallery settings."""
        try:
            data = request.get_json()
            display_mode = data.get("display_mode")
            change_rate = data.get("change_rate")

            if display_mode:
                gallery.set_display_mode(display_mode)
            if change_rate:
                gallery.set_change_rate(int(change_rate))

            return jsonify({"success": True}), 200
        except Exception as e:
            _log.error("Failed to update settings: %s", e)
            return jsonify({"error": "Failed to update settings"}), 500

    return app

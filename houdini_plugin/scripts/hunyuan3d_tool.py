# Tencent Hunyuan3D-2.1 Houdini Integration Studio Tool
# Provides PySide UI and handles async requests to FastAPI backend.

import sys
import os
import time
import requests
import json
import base64
import subprocess
import traceback
import tempfile

import hou

try:
    from PySide2 import QtCore, QtWidgets, QtGui
except ImportError:
    from PySide6 import QtCore, QtWidgets, QtGui

# Safe import for get_parent_window
def get_parent_window():
    if hasattr(hou, "qt") and hasattr(hou.qt, "mainWindow"):
        return hou.qt.mainWindow()
    return None

class GeneratorWorker(QtCore.QThread):
    progress_signal = QtCore.Signal(str)
    success_signal = QtCore.Signal(str, str) # uid, local_model_path
    error_signal = QtCore.Signal(str)

    def __init__(self, server_url, image_path, params, save_dir, asset_name):
        super(GeneratorWorker, self).__init__()
        self.server_url = server_url
        self.image_path = image_path
        self.params = params
        self.save_dir = save_dir
        self.asset_name = asset_name

    def run(self):
        try:
            # 1. Encode image
            self.progress_signal.emit("Encoding input image...")
            if not os.path.exists(self.image_path):
                self.error_signal.emit(f"Image file not found: {self.image_path}")
                return
            
            with open(self.image_path, "rb") as f:
                img_base64 = base64.b64encode(f.read()).decode()
            
            # 2. Build request parameters
            payload = {
                "image": img_base64,
                "texture": self.params.get("texture", True),
                "seed": self.params.get("seed", 1234),
                "guidance_scale": self.params.get("guidance_scale", 5.0),
                "num_inference_steps": self.params.get("num_inference_steps", 5),
                "octree_resolution": int(self.params.get("octree_resolution", 256)),
                "type": self.params.get("type", "glb"),
                "remove_background": True
            }
            
            # 3. Send to /send
            self.progress_signal.emit("Sending task to Hunyuan3D API...")
            send_url = f"{self.server_url.rstrip('/')}/send"
            
            try:
                response = requests.post(send_url, json=payload, timeout=20)
            except requests.exceptions.RequestException as re:
                self.error_signal.emit(f"Connection error: {str(re)}")
                return
                
            if response.status_code != 200:
                self.error_signal.emit(f"Server returned error {response.status_code}: {response.text}")
                return
            
            data = response.json()
            uid = data.get("uid")
            if not uid:
                self.error_signal.emit("Server response did not include a task UID.")
                return
            
            # 4. Poll status
            self.progress_signal.emit("Task submitted. Generation processing...")
            status_url = f"{self.server_url.rstrip('/')}/status/{uid}"
            
            max_retries = 300  # 5 minutes maximum
            retry_count = 0
            
            while retry_count < max_retries:
                time.sleep(1.5)
                retry_count += 1
                
                try:
                    status_resp = requests.get(status_url, timeout=5)
                    if status_resp.status_code != 200:
                        continue
                    
                    status_data = status_resp.json()
                    status_str = status_data.get("status")
                    
                    if status_str == "completed":
                        self.progress_signal.emit("Generation finished! Downloading model...")
                        model_base64 = status_data.get("model_base64")
                        if not model_base64:
                            self.error_signal.emit("Error: Server marked task as complete but returned no model data.")
                            return
                        
                        # Save model
                        ext = self.params.get("type", "glb")
                        local_filename = f"{self.asset_name}_{uid[:6]}.{ext}"
                        local_path = os.path.join(self.save_dir, local_filename)
                        
                        os.makedirs(self.save_dir, exist_ok=True)
                        with open(local_path, "wb") as f:
                            f.write(base64.b64decode(model_base64))
                        
                        self.success_signal.emit(uid, local_path)
                        return
                    
                    elif status_str == "texturing":
                        self.progress_signal.emit("Server Status: Texturing 3D model...")
                    elif status_str == "processing":
                        self.progress_signal.emit("Server Status: Reconstructing 3D geometry...")
                    elif status_str == "error":
                        msg = status_data.get("message", "Unknown backend generation error.")
                        self.error_signal.emit(f"Server side error: {msg}")
                        return
                        
                except requests.exceptions.RequestException:
                    # network glitch or server restarted, continue polling
                    pass
            
            self.error_signal.emit("Generation process timed out.")
            
        except Exception as e:
            self.error_signal.emit(f"Unexpected worker error: {str(e)}")

class Hunyuan3DDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(Hunyuan3DDialog, self).__init__(parent or get_parent_window())
        self.setWindowTitle("Hunyuan3D 2.1 Studio")
        self.setMinimumSize(480, 680)
        self.resize(520, 720)
        
        # Style sheet to match Houdini styling beautifully
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #dfdfdf;
                font-size: 11px;
            }
            QLabel#TitleLabel {
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
            }
            QLabel#SubtitleLabel {
                font-size: 11px;
                color: #888888;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #1b1b1b;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
                color: #ffffff;
                font-size: 11px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid #00a6ff;
            }
            QPushButton {
                background-color: #3e3e3e;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4f4f4f;
                border: 1px solid #777777;
            }
            QPushButton:pressed {
                background-color: #2b2b2b;
            }
            QPushButton#GenerateButton {
                background-color: #007acc;
                border: 1px solid #0098ff;
                padding: 10px;
                font-size: 13px;
            }
            QPushButton#GenerateButton:hover {
                background-color: #0096fa;
            }
            QPushButton#GenerateButton:disabled {
                background-color: #334e60;
                border: 1px solid #444444;
                color: #888888;
            }
            QGroupBox {
                border: 1px solid #444444;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11px;
                color: #b0b0b0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QTextEdit {
                background-color: #151515;
                border: 1px solid #333333;
                border-radius: 4px;
                color: #a0a0a0;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 10px;
            }
        """)

        self.setup_ui()
        
        # Start health check timer
        self.health_timer = QtCore.QTimer(self)
        self.health_timer.setInterval(2000)
        self.health_timer.timeout.connect(self.check_server_health)
        self.health_timer.start()
        
        # Keep track of worker thread
        self.worker = None

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)
        
        # 1. Header Title
        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setSpacing(2)
        
        title_label = QtWidgets.QLabel("Hunyuan3D 2.1 Studio")
        title_label.setObjectName("TitleLabel")
        subtitle_label = QtWidgets.QLabel("Fast Single-Image to textured 3D mesh reconstruction")
        subtitle_label.setObjectName("SubtitleLabel")
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        main_layout.addLayout(header_layout)
        
        # 2. Server Status Panel
        server_group = QtWidgets.QGroupBox("Hunyuan3D Backend Server")
        server_layout = QtWidgets.QVBoxLayout(server_group)
        server_layout.setContentsMargins(10, 15, 10, 10)
        server_layout.setSpacing(8)
        
        url_layout = QtWidgets.QHBoxLayout()
        url_layout.addWidget(QtWidgets.QLabel("Server Address:"))
        self.server_url_input = QtWidgets.QLineEdit("http://localhost:8081")
        url_layout.addWidget(self.server_url_input)
        
        # Status light and description
        status_layout = QtWidgets.QHBoxLayout()
        self.status_light = QtWidgets.QLabel()
        self.status_light.setFixedSize(12, 12)
        self.status_light.setStyleSheet("background-color: #e74c3c; border-radius: 6px;")
        
        self.status_text = QtWidgets.QLabel("Checking connection...")
        self.status_text.setStyleSheet("color: #aaaaaa; font-style: italic;")
        
        self.start_server_btn = QtWidgets.QPushButton("Start Server")
        self.start_server_btn.clicked.connect(self.start_backend_server)
        self.start_server_btn.setToolTip("Launches the local FastAPI backend server using the start_api_server.bat script.")
        
        status_layout.addWidget(self.status_light)
        status_layout.addWidget(self.status_text)
        status_layout.addStretch()
        status_layout.addWidget(self.start_server_btn)
        
        server_layout.addLayout(url_layout)
        server_layout.addLayout(status_layout)
        main_layout.addWidget(server_group)
        
        # 3. Input Image Section
        input_group = QtWidgets.QGroupBox("Input Source Image")
        input_layout = QtWidgets.QVBoxLayout(input_group)
        input_layout.setContentsMargins(10, 15, 10, 10)
        input_layout.setSpacing(8)
        
        path_layout = QtWidgets.QHBoxLayout()
        self.image_path_input = QtWidgets.QLineEdit()
        self.image_path_input.setPlaceholderText("Select image or grab from viewport...")
        self.image_path_input.textChanged.connect(self.on_image_path_changed)
        path_layout.addWidget(self.image_path_input)
        
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_image)
        path_layout.addWidget(browse_btn)
        
        grab_btn = QtWidgets.QPushButton("Grab Viewport")
        grab_btn.clicked.connect(self.grab_viewport)
        grab_btn.setToolTip("Takes a snapshot of the active Houdini Scene Viewer.")
        path_layout.addWidget(grab_btn)
        
        input_layout.addLayout(path_layout)
        
        # Image Preview Thumbnail
        self.preview_label = QtWidgets.QLabel("No Image Loaded")
        self.preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_label.setFixedSize(140, 140)
        self.preview_label.setStyleSheet("border: 1px dashed #555555; background-color: #1e1e1e; border-radius: 4px; color: #666666;")
        
        preview_container = QtWidgets.QHBoxLayout()
        preview_container.addStretch()
        preview_container.addWidget(self.preview_label)
        preview_container.addStretch()
        
        input_layout.addLayout(preview_container)
        main_layout.addWidget(input_group)
        
        # 4. Parameters Section
        params_group = QtWidgets.QGroupBox("Reconstruction Parameters")
        params_form = QtWidgets.QFormLayout(params_group)
        params_form.setContentsMargins(12, 15, 12, 12)
        params_form.setSpacing(8)
        
        self.texture_chk = QtWidgets.QCheckBox()
        self.texture_chk.setChecked(True)
        params_form.addRow("Generate Textures:", self.texture_chk)
        
        self.seed_spin = QtWidgets.QSpinBox()
        self.seed_spin.setRange(0, 2147483647)
        self.seed_spin.setValue(1234)
        params_form.addRow("Random Seed:", self.seed_spin)
        
        self.guidance_spin = QtWidgets.QDoubleSpinBox()
        self.guidance_spin.setRange(1.0, 20.0)
        self.guidance_spin.setValue(5.0)
        self.guidance_spin.setSingleStep(0.5)
        params_form.addRow("Guidance Scale:", self.guidance_spin)
        
        self.steps_spin = QtWidgets.QSpinBox()
        self.steps_spin.setRange(1, 100)
        self.steps_spin.setValue(5)
        params_form.addRow("Inference Steps:", self.steps_spin)
        
        self.resolution_combo = QtWidgets.QComboBox()
        self.resolution_combo.addItems(["128", "256", "512", "1024"])
        self.resolution_combo.setCurrentText("256")
        params_form.addRow("Octree Resolution:", self.resolution_combo)
        
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(["glb", "obj"])
        self.format_combo.setCurrentText("glb")
        params_form.addRow("Output Mesh Format:", self.format_combo)
        
        main_layout.addWidget(params_group)
        
        # 5. Output / Import Pipeline Section
        output_group = QtWidgets.QGroupBox("Scene Import Pipeline Settings")
        output_form = QtWidgets.QFormLayout(output_group)
        output_form.setContentsMargins(12, 15, 12, 12)
        output_form.setSpacing(8)
        
        self.asset_name_input = QtWidgets.QLineEdit("hunyuan_asset")
        output_form.addRow("Asset Name (Node):", self.asset_name_input)
        
        # Save directory path
        save_dir_layout = QtWidgets.QHBoxLayout()
        self.save_dir_input = QtWidgets.QLineEdit()
        self.update_default_save_dir()
        save_dir_layout.addWidget(self.save_dir_input)
        
        browse_dir_btn = QtWidgets.QPushButton("...")
        browse_dir_btn.setFixedWidth(30)
        browse_dir_btn.clicked.connect(self.browse_save_dir)
        save_dir_layout.addWidget(browse_dir_btn)
        
        output_form.addRow("Save Geometry to:", save_dir_layout)
        
        self.import_chk = QtWidgets.QCheckBox()
        self.import_chk.setChecked(True)
        output_form.addRow("Auto-Import to Scene:", self.import_chk)
        
        self.camera_chk = QtWidgets.QCheckBox()
        self.camera_chk.setChecked(True)
        output_form.addRow("Create Matched Camera:", self.camera_chk)
        
        main_layout.addWidget(output_group)
        
        # 6. Action and Log Console
        self.generate_btn = QtWidgets.QPushButton("Generate 3D Model")
        self.generate_btn.setObjectName("GenerateButton")
        self.generate_btn.clicked.connect(self.start_generation)
        main_layout.addWidget(self.generate_btn)
        
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)
        
        self.log_console = QtWidgets.QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(80)
        self.log_console.setPlaceholderText("System status messages...")
        main_layout.addWidget(self.log_console)

    def log(self, text):
        self.log_console.append(text)
        # Scroll to bottom
        scrollbar = self.log_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_default_save_dir(self):
        try:
            hip_dir = hou.expandString("$HIP")
            if hip_dir == "." or not hip_dir:
                hip_dir = os.path.expanduser("~/Hunyuan3D_Output")
            else:
                hip_dir = os.path.join(hip_dir, "hunyuan3d_output")
            self.save_dir_input.setText(os.path.abspath(hip_dir))
        except Exception:
            self.save_dir_input.setText(os.path.expanduser("~/Hunyuan3D_Output"))

    def check_server_health(self):
        # Prevent checking connection during active worker generation (which might block server)
        if self.worker and self.worker.isRunning():
            return
            
        url = self.server_url_input.text().strip()
        try:
            resp = requests.get(f"{url.rstrip('/')}/health", timeout=1.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "healthy":
                    self.set_server_status(True, f"Connected (Worker: {data.get('worker_id', 'healthy')})")
                    return
        except Exception:
            pass
        self.set_server_status(False, "Disconnected")

    def set_server_status(self, connected, text):
        if connected:
            self.status_light.setStyleSheet("background-color: #2ecc71; border-radius: 6px; border: 1px solid #1f8a4c;")
            self.status_text.setText(text)
            self.status_text.setStyleSheet("color: #2ecc71; font-weight: bold;")
            self.start_server_btn.setEnabled(False)
            if not (self.worker and self.worker.isRunning()):
                self.generate_btn.setEnabled(True)
        else:
            self.status_light.setStyleSheet("background-color: #e74c3c; border-radius: 6px; border: 1px solid #b03a2e;")
            self.status_text.setText("Disconnected")
            self.status_text.setStyleSheet("color: #e74c3c; font-weight: bold;")
            self.start_server_btn.setEnabled(True)
            self.generate_btn.setEnabled(False)

    def start_backend_server(self):
        try:
            # Locate start_api_server.bat relative to this script
            script_path = os.path.abspath(__file__)
            # hunyuan3d_tool.py is in /houdini_plugin/scripts/
            plugin_dir = os.path.dirname(os.path.dirname(script_path))
            repo_root = os.path.dirname(plugin_dir)
            bat_path = os.path.join(repo_root, "start_api_server.bat")
            
            if not os.path.exists(bat_path):
                self.log(f"Error: Server script not found at {bat_path}")
                return
                
            self.log(f"Launching backend server: {bat_path}")
            
            # Start process asynchronously in a new terminal window
            if sys.platform == "win32":
                subprocess.Popen(["cmd.exe", "/c", "start", "Hunyuan3D API Server", bat_path], cwd=repo_root)
            else:
                # Fallback for macOS/Linux (though requirements specify Windows)
                subprocess.Popen(["bash", bat_path], cwd=repo_root)
                
            self.log("Server startup command sent. Waiting for server to initialize...")
        except Exception as e:
            self.log(f"Failed to start backend server: {str(e)}")

    def browse_image(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if filename:
            self.image_path_input.setText(filename)
            self.update_image_preview(filename)

    def browse_save_dir(self):
        dirname = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Save Directory", self.save_dir_input.text()
        )
        if dirname:
            self.save_dir_input.setText(os.path.abspath(dirname))

    def on_image_path_changed(self, text):
        if os.path.exists(text) and os.path.isfile(text):
            self.update_image_preview(text)

    def update_image_preview(self, path):
        pixmap = QtGui.QPixmap(path)
        if not pixmap.isNull():
            # Scale pixmap keeping aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.preview_label.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled_pixmap)
            self.preview_label.setText("") # Clear text
        else:
            self.preview_label.setPixmap(QtGui.QPixmap())
            self.preview_label.setText("Invalid Image")

    def grab_viewport(self):
        try:
            # Find scene viewer pane
            pane = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
            if pane is None:
                self.log("Error: No active Scene Viewer found. Please open a viewport.")
                return
                
            viewport = pane.curViewport()
            if viewport is None:
                self.log("Error: No active viewport in the Scene Viewer.")
                return
                
            # Create a temp file path
            temp_dir = tempfile.gettempdir()
            temp_png = os.path.join(temp_dir, f"hunyuan3d_grab_{int(time.time())}.png")
            
            # Save viewport image (Houdini Python command)
            self.log("Grabbing active viewport frame...")
            viewport.saveImage(temp_png)
            
            if os.path.exists(temp_png):
                self.image_path_input.setText(temp_png)
                self.update_image_preview(temp_png)
                self.log(f"Successfully grabbed viewport frame to: {temp_png}")
            else:
                self.log("Error: Viewport grab did not generate a file. Try saving viewport frame manually.")
        except Exception as e:
            self.log(f"Viewport grab failed: {str(e)}")
            traceback.print_exc()

    def start_generation(self):
        image_path = self.image_path_input.text().strip()
        if not image_path or not os.path.exists(image_path):
            QtWidgets.QMessageBox.warning(self, "Missing Image", "Please select or grab an input image first.")
            return
            
        save_dir = self.save_dir_input.text().strip()
        if not save_dir:
            QtWidgets.QMessageBox.warning(self, "Missing Directory", "Please select a valid output directory.")
            return
            
        asset_name = self.asset_name_input.text().strip()
        if not asset_name:
            asset_name = "hunyuan_asset"
            
        params = {
            "texture": self.texture_chk.isChecked(),
            "seed": self.seed_spin.value(),
            "guidance_scale": self.guidance_spin.value(),
            "num_inference_steps": self.steps_spin.value(),
            "octree_resolution": int(self.resolution_combo.currentText()),
            "type": self.format_combo.currentText()
        }
        
        server_url = self.server_url_input.text().strip()
        
        # Disable UI
        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating 3D Model...")
        self.progress_bar.setRange(0, 0) # Indeterminate busy state
        self.progress_bar.show()
        
        # Launch background worker thread
        self.worker = GeneratorWorker(server_url, image_path, params, save_dir, asset_name)
        self.worker.progress_signal.connect(self.on_worker_progress)
        self.worker.success_signal.connect(self.on_worker_success)
        self.worker.error_signal.connect(self.on_worker_error)
        self.worker.start()
        
        self.log(f"Started generation worker. Asset: {asset_name}, Format: {params['type']}")

    def on_worker_progress(self, msg):
        self.log(msg)

    def on_worker_success(self, uid, file_path):
        self.progress_bar.hide()
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("Generate 3D Model")
        
        self.log(f"3D Model saved to: {file_path}")
        
        # Execute Scene Integration pipeline
        try:
            self.import_model_to_houdini(file_path)
            if self.camera_chk.isChecked():
                self.import_camera_to_houdini(uid)
            
            QtWidgets.QMessageBox.information(
                self, "Success", 
                f"3D reconstruction complete!\nModel saved and imported successfully as '{self.asset_name_input.text()}'."
            )
        except Exception as e:
            self.log(f"Integration failed: {str(e)}")
            QtWidgets.QMessageBox.warning(self, "Integration Error", f"Model generated but import failed: {str(e)}")

    def on_worker_error(self, err_msg):
        self.progress_bar.hide()
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("Generate 3D Model")
        self.log(f"ERROR: {err_msg}")
        QtWidgets.QMessageBox.critical(self, "Generation Failed", f"Failed to generate 3D model:\n{err_msg}")

    def import_model_to_houdini(self, file_path):
        if not self.import_chk.isChecked():
            return
            
        self.log("Importing mesh to Houdini scene...")
        
        # Use forward slashes for Houdini paths
        file_path_clean = file_path.replace("\\", "/")
        asset_name = self.asset_name_input.text().strip() or "hunyuan_asset"
        
        obj = hou.node("/obj")
        
        # Check if node already exists
        geo = obj.node(asset_name)
        if geo is None:
            geo = obj.createNode("geo", node_name=asset_name)
        
        # Create or update File SOP inside
        file_sop = geo.node("load_model")
        if file_sop is None:
            # Look for default file1 created by Houdini
            file_sop = geo.node("file1")
            if file_sop is not None:
                file_sop.setName("load_model")
            else:
                file_sop = geo.createNode("file", node_name="load_model")
                
        file_sop.parm("file").set(file_path_clean)
        
        # Setup display/render flags
        file_sop.setDisplayFlag(True)
        file_sop.setRenderFlag(True)
        
        geo.layoutChildren()
        self.log(f"Imported model to SOP node: {geo.path()}")

    def import_camera_to_houdini(self, uid):
        self.log("Fetching matching camera script from server...")
        server_url = self.server_url_input.text().strip()
        cam_url = f"{server_url.rstrip('/')}/camera/{uid}"
        
        try:
            resp = requests.get(cam_url, timeout=10)
            if resp.status_code == 200:
                script_content = resp.text
                self.log("Running camera script...")
                
                # Execute the camera script in a local dictionary containing hou
                local_namespace = {"hou": hou}
                exec(script_content, local_namespace)
                
                self.log("Camera created/aligned successfully.")
            else:
                self.log(f"Warning: Could not fetch camera script (HTTP {resp.status_code}).")
        except Exception as e:
            self.log(f"Warning: Camera script execution failed: {str(e)}")

# Global dialog reference to prevent garbage collection
_dialog = None

def show_dialog():
    global _dialog
    if _dialog is not None:
        try:
            _dialog.close()
        except Exception:
            pass
    
    _dialog = Hunyuan3DDialog()
    _dialog.show()

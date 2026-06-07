# Hunyuan3D 2.1 Studio for Houdini

A native Houdini plugin integration for Tencent's Hunyuan3D-2.1. This plugin allows artists to generate textured 3D assets directly from reference images or viewport snapshots in a single click, integrating them seamlessly into their SOP geometry networks.

---

## 🚀 Key Features

* **Single-Click Installer:** Installs the plugin package for all detected Houdini versions on Windows.
* **Non-Blocking Threading:** Generation tasks run asynchronously in a background thread, ensuring Houdini's UI never freezes during reconstruction.
* **Interactive PySide UI:** Clean UI with parameters matching Hunyuan3D's backend server settings (seed, texture generation, guidance scale, steps, resolution).
* **Viewport Grabber:** Take a snapshot of the current active Houdini scene view and use it instantly as a generation reference image.
* **Automated SOP Pipeline:** Automatically imports generated models (GLB or OBJ) into a Geometry (`geo`) network with a `File` SOP configured.
* **Camera Projection Setup:** Dynamically downloads and executes the camera transform script from the backend server to align a Houdini camera to match the projection reference perfectly.

---

## 🛠️ Installation

1. Double-click the **`install_houdini.bat`** file located in the root of the repository.
2. The installer will automatically scan your local and OneDrive Documents directories for active Houdini directories (`houdini20.5`, `houdini21.0`, etc.) and register the plugin.
3. Once the installer displays a success message, you're ready!

---

## 📖 How to Use

### 1. Start the Backend API Server
* Run the **`start_api_server.bat`** script in the repository root to start the model server.
* *Alternative:* Launch Houdini, open the Hunyuan3D tool, and click **"Start Server"** inside the UI panel to launch it automatically.

### 2. Launch the Tool in Houdini
* Open Houdini.
* You will see a new shelf tab named **`Hunyuan3D`** at the top.
* Click the **`Hunyuan3D 2.1`** shelf tool.
* *If the shelf is hidden:* Click the `+` button on your shelf list, select **Shelves**, and check **Hunyuan3D**.

### 3. Generate 3D Assets
1. **Source Image:** Click **Browse...** to select an image from your computer, or click **Grab Viewport** to screenshot your current Houdini viewer.
2. **Parameters:** Adjust seeds, texture toggle, inference steps, and octree resolution.
3. **Pipeline Settings:** Change the asset name, toggle automatic mesh import, and toggle camera matching.
4. Click **Generate 3D Model**.
5. Once completed, a new `/obj/<asset_name>` geometry node and matching `/obj/Generated_Camera` will appear in your scene!

### 4. Using the Native SOP Node (HDA)
You can also generate geometry procedurally inside your SOP node networks:
1. Create or go into any Geometry (`geo`) node.
2. In the Network Editor, press **`Tab`** and search for **`Hunyuan3D 2.1 Generator`** (or type `hunyuan3d`) to place the node.
3. Select the node and configure the parameters in the **Parameter Pane**:
   * Set the **Source Image** path.
   * Toggle **Generate Textures**, adjust **Seed**, **Guidance Scale**, and **Octree Resolution**.
   * Define the **Output Directory** (defaults to `$HIP/hunyuan3d_output`).
4. Click the **Generate 3D Model** button.
5. A native Houdini progress bar will open. Once completed, the node will load the generated geometry and output it directly into the next SOP node in your chain!

---

## 📂 Directory Structure

```text
houdini_plugin/
├── toolbar/
│   └── hunyuan3d.shelf        # Defines the shelf button and launch script
├── scripts/
│   └── hunyuan3d_tool.py      # Core PySide interface and integration code
├── otls/
│   └── hunyuan3d.hda          # Compiled native Houdini SOP node digital asset
└── packages/
    └── hunyuan3d.json         # Package definition file (pointing to this folder)
```

## ❓ Troubleshooting

### The shelf tab is missing
* Go to the shelf set at the top of the interface. Click the `+` icon -> **Shelves** -> and verify that **Hunyuan3D** is ticked.
* Verify that `hunyuan3d.json` exists in `C:\Users\<YourUsername>\Documents\houdiniX.Y\packages\hunyuan3d.json`.

### Error: "No module named 'requests'" inside Houdini
* Houdini uses its own Python environment. If you encounter missing packages:
  * Open Houdini's **Command Line Tools** (hython) and run:
    ```bash
    hython -m pip install requests
    ```
  * Or install it to your system Python.

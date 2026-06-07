# HDA builder script for Hunyuan3D SOP node.
# Run this inside Houdini's Python interpreter (hython.exe).

import os
import sys

# Import Houdini python library (only works in hython)
import hou

def main():
    if len(sys.argv) < 2:
        print("Usage: hython generate_hda.py <output_hda_path>")
        sys.exit(1)
        
    hda_path = os.path.abspath(sys.argv[1])
    print(f"Creating HDA at: {hda_path}")
    
    # 1. Create a dummy SOP network to host the digital asset definition
    obj = hou.node("/obj")
    # In case there's an existing node, clean up
    temp_geo = obj.node("temp_geo_builder")
    if temp_geo:
        temp_geo.destroy()
        
    geo = obj.createNode("geo", "temp_geo_builder")
    
    # We want to create a custom Geometry SOP digital asset.
    # To do that, we create a subnet inside the geo node.
    subnet = geo.createNode("subnet", "hunyuan3d_generator")
    
    # 2. Inside the subnet, create a GLTF SOP, Null SOP, and Switch SOP to bypass empty/missing files
    gltf_sop = subnet.createNode("gltf", "load_cached_glb")
    null_empty = subnet.createNode("null", "EMPTY_GEOMETRY")
    switch_sop = subnet.createNode("switch", "switch_geometry")
    
    switch_sop.setInput(0, null_empty)
    switch_sop.setInput(1, gltf_sop)
    
    null_sop = subnet.createNode("null", "OUT")
    null_sop.setInput(0, switch_sop)
    null_sop.setDisplayFlag(True)
    null_sop.setRenderFlag(True)
    
    gltf_sop.parm("filename").setExpression('chs("../generated_file")')
    
    # Select Input 1 (GLTF SOP) only if the file exists, else Input 0 (Empty Null SOP)
    expr_code = '1 if (hou.node("../load_cached_glb").evalParm("filename") and __import__("os").path.exists(hou.expandString(hou.node("../load_cached_glb").evalParm("filename")))) else 0'
    switch_sop.parm("input").setExpression(expr_code, language=hou.exprLanguage.Python)
    
    # Layout internal nodes
    subnet.layoutChildren()
    
    # 3. Create parameter template group
    group = hou.ParmTemplateGroup()
    
    # Server tab
    folder_server = hou.FolderParmTemplate("server_folder", "Server Configuration")
    folder_server.addParmTemplate(hou.StringParmTemplate("server_url", "Server URL", 1, default_value=(["http://localhost:8081"])))
    
    btn_start_server = hou.ButtonParmTemplate("start_server", "Start Server")
    btn_start_server.setScriptCallback("hou.phm().start_server(hou.node('.'))")
    btn_start_server.setScriptCallbackLanguage(hou.scriptLanguage.Python)
    folder_server.addParmTemplate(btn_start_server)
    
    group.append(folder_server)
    
    # Settings tab
    folder_params = hou.FolderParmTemplate("params_folder", "Reconstruction Settings")
    folder_params.addParmTemplate(hou.ToggleParmTemplate("texture", "Generate Textures", True))
    folder_params.addParmTemplate(hou.IntParmTemplate("seed", "Seed", 1, default_value=([1234])))
    folder_params.addParmTemplate(hou.FloatParmTemplate("guidance_scale", "Guidance Scale", 1, default_value=([5.0])))
    folder_params.addParmTemplate(hou.IntParmTemplate("steps", "Inference Steps", 1, default_value=([5])))
    
    res_items = ["128", "256", "512", "1024"]
    res_labels = ["128", "256 (Default)", "512", "1024"]
    folder_params.addParmTemplate(hou.StringParmTemplate("resolution", "Octree Resolution", 1,
        string_type=hou.stringParmType.Regular,
        menu_items=res_items,
        menu_labels=res_labels,
        default_value=(["256"])
    ))
    
    fmt_items = ["glb", "obj"]
    fmt_labels = ["GLB (Textured)", "OBJ"]
    folder_params.addParmTemplate(hou.StringParmTemplate("format", "Output Format", 1,
        string_type=hou.stringParmType.Regular,
        menu_items=fmt_items,
        menu_labels=fmt_labels,
        default_value=(["glb"])
    ))
    group.append(folder_params)
    
    # Input/Output tab
    folder_image = hou.FolderParmTemplate("image_folder", "Input / Output")
    folder_image.addParmTemplate(hou.StringParmTemplate("image_path", "Source Image", 1, string_type=hou.stringParmType.FileReference))
    folder_image.addParmTemplate(hou.StringParmTemplate("save_dir", "Output Directory", 1,
        string_type=hou.stringParmType.FileReference,
        default_value=(["$HIP/hunyuan3d_output"])
    ))
    folder_image.addParmTemplate(hou.StringParmTemplate("asset_name", "Asset Name", 1, default_value=(["hunyuan_asset"])))
    folder_image.addParmTemplate(hou.StringParmTemplate("generated_file", "Generated Model Path", 1, string_type=hou.stringParmType.FileReference))
    group.append(folder_image)
    
    # Action Button
    btn_generate = hou.ButtonParmTemplate("generate", "Generate 3D Model")
    btn_generate.setScriptCallback("hou.phm().generate_model(hou.node('.'))")
    btn_generate.setScriptCallbackLanguage(hou.scriptLanguage.Python)
    group.append(btn_generate)
    
    # Assign the parameter templates to the subnet
    subnet.setParmTemplateGroup(group)
    
    # 4. Create the digital asset (.hda)
    hda_dir = os.path.dirname(hda_path)
    if not os.path.exists(hda_dir):
        os.makedirs(hda_dir)
        
    print("Creating digital asset definition...")
    hda_node = subnet.createDigitalAsset(
        name="hunyuan3d_generator",
        hda_file_name=hda_path,
        description="Hunyuan3D 2.1 Generator",
        min_num_inputs=0,
        max_num_inputs=0,
        compress_contents=True
    )
    
    # Get the definition object
    definition = hda_node.type().definition()
    definition.setParmTemplateGroup(group)
    
    # 5. Define embedded python script content for the HDA's PythonModule
    python_module_code = '''# Python Module for Hunyuan3D SOP node.
# Handles asynchronous requests to the FastAPI server and loading the geometry.

import os
import time
import base64
import requests
import hou

def display_message(text, severity=None):
    if hasattr(hou, 'ui'):
        if severity is not None:
            hou.ui.displayMessage(text, severity=severity)
        else:
            hou.ui.displayMessage(text)
    else:
        prefix = "[ERROR] " if (severity == hou.severityType.Error) else ""
        print(f"{prefix}{text}")

def set_status_message(text, severity=None):
    if hasattr(hou, 'ui'):
        if severity is not None:
            hou.ui.setStatusMessage(text, severity=severity)
        else:
            hou.ui.setStatusMessage(text)
    else:
        print(f"[STATUS] {text}")

def ensure_server_running(node, operation=None):
    import requests
    import subprocess
    import sys
    
    server_url = node.parm("server_url").eval().strip()
    
    # 1. Check if it's already healthy
    try:
        resp = requests.get(f"{server_url}/health", timeout=0.5)
        if resp.status_code == 200 and resp.json().get("status") == "healthy":
            return True
    except Exception:
        pass
        
    # 2. It's not healthy. Locate start_api_server.bat
    definition = node.type().definition()
    if not definition:
        return False
        
    hda_path = definition.libraryFilePath()
    current_dir = os.path.dirname(os.path.abspath(hda_path))
    bat_path = None
    repo_root = None
    for _ in range(5):
        candidate = os.path.join(current_dir, "start_api_server.bat")
        if os.path.exists(candidate):
            bat_path = candidate
            repo_root = current_dir
            break
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
        
    if not bat_path or not repo_root:
        if operation:
            set_status_message("Error: Could not find start_api_server.bat in parent directories.")
        return False
        
    # Start the server
    if operation:
        set_status_message("Starting Hunyuan3D API server subprocess...")
    try:
        env = os.environ.copy()
        for var in ["PYTHONPATH", "PYTHONHOME"]:
            if var in env:
                del env[var]
        if sys.platform == "win32":
            subprocess.Popen(["cmd.exe", "/c", "start", "Hunyuan3D API Server", bat_path], cwd=repo_root, env=env)
        else:
            subprocess.Popen(["bash", bat_path], cwd=repo_root, env=env)
    except Exception as e:
        if operation:
            set_status_message(f"Failed to start server process: {str(e)}")
        return False
        
    # 3. Poll /health until healthy or timeout (3 mins)
    max_wait = 180
    start_time = time.time()
    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)
        msg = f"Hunyuan3D: Waiting for server to load checkpoints ({elapsed}s elapsed, takes ~1-2 mins)..."
        set_status_message(msg)
        if operation:
            progress = 0.05 + (0.15 * (elapsed / float(max_wait)))
            operation.updateProgress(progress)
            
        time.sleep(2)
        try:
            resp = requests.get(f"{server_url}/health", timeout=1.0)
            if resp.status_code == 200 and resp.json().get("status") == "healthy":
                return True
        except Exception:
            pass
            
    return False

def start_server(node):
    try:
        import requests
        import subprocess
        import sys
        server_url = node.parm("server_url").eval().strip()
        try:
            resp = requests.get(f"{server_url}/health", timeout=0.5)
            if resp.status_code == 200 and resp.json().get("status") == "healthy":
                display_message("Hunyuan3D server is already running and healthy!")
                return
        except Exception:
            pass
            
        definition = node.type().definition()
        if not definition:
            display_message("Error: Could not obtain HDA definition.", severity=hou.severityType.Error)
            return
            
        hda_path = definition.libraryFilePath()
        current_dir = os.path.dirname(os.path.abspath(hda_path))
        bat_path = None
        repo_root = None
        for _ in range(5):
            candidate = os.path.join(current_dir, "start_api_server.bat")
            if os.path.exists(candidate):
                bat_path = candidate
                repo_root = current_dir
                break
            parent = os.path.dirname(current_dir)
            if parent == current_dir:
                break
            current_dir = parent
            
        if bat_path and repo_root:
            set_status_message("Starting Hunyuan3D API server in new window...", severity=hou.severityType.ImportantMessage)
            env = os.environ.copy()
            for var in ["PYTHONPATH", "PYTHONHOME"]:
                if var in env:
                    del env[var]
            if sys.platform == "win32":
                subprocess.Popen(["cmd.exe", "/c", "start", "Hunyuan3D API Server", bat_path], cwd=repo_root, env=env)
            else:
                subprocess.Popen(["bash", bat_path], cwd=repo_root, env=env)
            display_message("Hunyuan3D API server started. Please wait about 2 minutes for checkpoints to finish loading before generating meshes.")
        else:
            display_message("Error: Could not find start_api_server.bat in parent directories.", severity=hou.severityType.Error)
    except Exception as e:
        display_message(f"Failed to start server: {str(e)}", severity=hou.severityType.Error)

def generate_model(node):
    # Read parameters
    server_url = node.parm("server_url").eval().strip()
    image_path = node.parm("image_path").eval().strip()
    texture = bool(node.parm("texture").eval())
    seed = int(node.parm("seed").eval())
    guidance_scale = float(node.parm("guidance_scale").eval())
    steps = int(node.parm("steps").eval())
    resolution = node.parm("resolution").eval()
    file_format = node.parm("format").eval()
    save_dir = node.parm("save_dir").eval().strip()
    asset_name = node.parm("asset_name").eval().strip()
    
    # Validate inputs
    if not image_path:
        display_message("Error: Please select a source image path.", severity=hou.severityType.Error)
        return
        
    image_path_expanded = hou.expandString(image_path)
    if not os.path.exists(image_path_expanded):
        display_message(f"Error: Source image file does not exist: {image_path_expanded}", severity=hou.severityType.Error)
        return
        
    save_dir_expanded = hou.expandString(save_dir)
    
    # Execute generation process inside an interruptable Houdini progress dialog
    with hou.InterruptableOperation("Generating Hunyuan3D Asset", open_interrupt_dialog=True) as operation:
        try:
            # First ensure server is running and healthy
            operation.updateProgress(0.05)
            if not ensure_server_running(node, operation):
                display_message("Error: Could not connect to API server. Please verify start_api_server.bat runs correctly.", severity=hou.severityType.Error)
                return
                
            set_status_message("Hunyuan3D: Encoding input image...")
            operation.updateProgress(0.2)
            with open(image_path_expanded, "rb") as f:
                img_base64 = base64.b64encode(f.read()).decode()
                
            payload = {
                "image": img_base64,
                "texture": texture,
                "seed": seed,
                "guidance_scale": guidance_scale,
                "num_inference_steps": steps,
                "octree_resolution": int(resolution),
                "type": file_format,
                "remove_background": True
            }
            
            set_status_message("Hunyuan3D: Submitting task to backend server...")
            operation.updateProgress(0.25)
            send_url = f"{server_url.rstrip('/')}/send"
            
            try:
                response = requests.post(send_url, json=payload, timeout=20)
            except requests.exceptions.RequestException as re:
                display_message(f"Connection Failed: Could not connect to API server at {server_url}.\\n\\nDetails: {str(re)}", severity=hou.severityType.Error)
                return
                
            if response.status_code != 200:
                display_message(f"Server Error (HTTP {response.status_code}): {response.text}", severity=hou.severityType.Error)
                return
                
            data = response.json()
            uid = data.get("uid")
            if not uid:
                display_message("Server did not return a valid task UID.", severity=hou.severityType.Error)
                return
                
            # Polling status loop
            status_url = f"{server_url.rstrip('/')}/status/{uid}"
            max_retries = 300
            retry = 0
            
            while retry < max_retries:
                if operation:
                    # Periodically update progress to check for user cancellation
                    operation.updateProgress(0.3 + (0.5 * (retry / float(max_retries))))
                    
                time.sleep(1.5)
                retry += 1
                
                try:
                    status_resp = requests.get(status_url, timeout=5)
                    if status_resp.status_code != 200:
                        continue
                        
                    status_data = status_resp.json()
                    status_str = status_data.get("status")
                    
                    if status_str == "completed":
                        set_status_message("Hunyuan3D: Downloading reconstructed model...")
                        operation.updateProgress(0.9)
                        model_base64 = status_data.get("model_base64")
                        if not model_base64:
                            display_message("Error: Completed task returned no model base64 data.", severity=hou.severityType.Error)
                            return
                            
                        # Save model
                        os.makedirs(save_dir_expanded, exist_ok=True)
                        output_filename = f"{asset_name}_{uid[:6]}.{file_format}"
                        output_path = os.path.join(save_dir_expanded, output_filename)
                        output_path_clean = output_path.replace("\\\\", "/").replace("\\\\", "/")
                        
                        with open(output_path, "wb") as f:
                            f.write(base64.b64decode(model_base64))
                            
                        # Update the top-level HDA parameter
                        node.parm("generated_file").set(output_path_clean)
                            
                        # Dynamic camera alignment script download and execution
                        cam_url = f"{server_url.rstrip('/')}/camera/{uid}"
                        try:
                            cam_resp = requests.get(cam_url, timeout=5)
                            if cam_resp.status_code == 200:
                                # Execute the camera alignment script in the parent scene
                                script_content = cam_resp.text
                                local_ns = {"hou": hou}
                                exec(script_content, local_ns)
                        except Exception:
                            pass
                            
                        display_message(f"Reconstruction successful! Model loaded into network:\\n{output_path_clean}", severity=hou.severityType.Message)
                        break
                        
                    elif status_str == "texturing":
                        set_status_message("Hunyuan3D: Generating textures...")
                        operation.updateProgress(0.6)
                    elif status_str == "processing":
                        set_status_message("Hunyuan3D: Reconstructing 3D geometry...")
                        operation.updateProgress(0.4)
                    elif status_str == "error":
                        msg = status_data.get("message", "Backend error.")
                        display_message(f"Generation failed: {msg}", severity=hou.severityType.Error)
                        break
                        
                except requests.exceptions.RequestException:
                    pass # Keep polling despite network hiccups
                    
            if retry >= max_retries:
                display_message("Error: Generation timed out on the server.", severity=hou.severityType.Error)
                
        except hou.OperationInterrupted:
            set_status_message("Generation cancelled by user.")
        except Exception as e:
            display_message(f"Unexpected error: {str(e)}", severity=hou.severityType.Error)
'''
    
    # 6. Define embedded python script content for the HDA's OnCreated event
    on_created_code = '''# OnCreated script for Hunyuan3D SOP node.
# Automatically checks if the API server is running, and starts it if not.

import os
import subprocess
import requests
import hou

def check_and_start_server():
    server_url = "http://localhost:8081"
    try:
        resp = requests.get(f"{server_url}/health", timeout=0.5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "healthy":
                # Server is already running and healthy
                return
    except Exception:
        pass
        
    # Server is not running, let's start it
    try:
        node = kwargs.get('node')
        if not node:
            return
            
        definition = node.type().definition()
        if not definition:
            return
            
        hda_path = definition.libraryFilePath()
        current_dir = os.path.dirname(os.path.abspath(hda_path))
        bat_path = None
        repo_root = None
        for _ in range(5):
            candidate = os.path.join(current_dir, "start_api_server.bat")
            if os.path.exists(candidate):
                bat_path = candidate
                repo_root = current_dir
                break
            parent = os.path.dirname(current_dir)
            if parent == current_dir:
                break
            current_dir = parent
            
        if bat_path and repo_root:
            import sys
            if hasattr(hou, 'ui'):
                hou.ui.setStatusMessage("Hunyuan3D server not running. Starting API server...", hou.severityType.ImportantMessage)
            else:
                print("[STATUS] Hunyuan3D server not running. Starting API server...")
            
            env = os.environ.copy()
            for var in ["PYTHONPATH", "PYTHONHOME"]:
                if var in env:
                    del env[var]
            # Start process asynchronously in a new terminal window
            if sys.platform == "win32":
                subprocess.Popen(["cmd.exe", "/c", "start", "Hunyuan3D API Server", bat_path], cwd=repo_root, env=env)
            else:
                subprocess.Popen(["bash", bat_path], cwd=repo_root, env=env)
    except Exception as e:
        print("Failed to auto-start Hunyuan3D server:", str(e))

check_and_start_server()
'''

    print("Writing PythonModule section to digital asset...")
    definition.addSection("PythonModule", python_module_code)
    
    print("Writing OnCreated.py section to digital asset...")
    definition.addSection("OnCreated.py", on_created_code)
    
    # Save the changes
    definition.save(definition.libraryFilePath())
    print("HDA created and saved successfully.")
    
    # Clean up builder geometry node
    geo.destroy()

if __name__ == "__main__":
    main()

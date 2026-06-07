# Hunyuan3D 2.1 Houdini Plugin Installer
# Automatically configures the Houdini package JSON pointing to this repository.

import os
import sys
import glob
import json

def get_documents_dirs():
    dirs = []
    # Standard home documents
    home = os.path.expanduser("~")
    dirs.append(os.path.join(home, "Documents"))
    dirs.append(os.path.join(home, "OneDrive", "Documents"))
    
    # Try using ctypes to get standard shell folders on Windows
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            CSIDL_PERSONAL = 5       # My Documents
            SHGFP_TYPE_CURRENT = 0   # Current value, not default
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf)
            if buf.value and buf.value not in dirs:
                dirs.insert(0, buf.value)
        except Exception:
            pass
            
    # Filter unique existing directories
    valid_dirs = []
    for d in dirs:
        if os.path.exists(d) and d not in valid_dirs:
            valid_dirs.append(d)
    return valid_dirs

def compile_hda(current_dir, plugin_dir):
    print("\n--- Compiling Houdini Digital Asset (HDA) ---")
    hda_path = os.path.join(plugin_dir, "otls", "hunyuan3d.hda")
    generator_script = os.path.join(current_dir, "generate_hda.py")
    
    if not os.path.exists(generator_script):
        print("Warning: generate_hda.py script not found. Skipping compilation.")
        return
        
    hython_paths = []
    if sys.platform == "win32":
        search_pattern = "C:\\Program Files\\Side Effects Software\\Houdini*\\bin\\hython.exe"
        hython_paths = glob.glob(search_pattern)
        
    if not hython_paths:
        print("Warning: Could not automatically locate hython.exe in default paths.")
        print("Using the pre-compiled HDA file already included in the package.")
        return
        
    hython_paths.sort(reverse=True)
    hython_exe = hython_paths[0]
    print(f"Using Houdini Compiler: {hython_exe}")
    
    import subprocess
    try:
        print("Compiling native SOP node (HDA)...")
        res = subprocess.run([hython_exe, generator_script, hda_path], capture_output=True, text=True)
        if res.returncode == 0:
            print("HDA Compilation successful!")
        else:
            print(f"Warning: HDA compilation failed: {res.stderr}")
            print("The package will fallback to using the pre-compiled version if available.")
    except Exception as e:
        print(f"Warning: HDA compilation failed: {e}")
        print("The package will fallback to using the pre-compiled version if available.")

def main():
    print("==========================================================")
    print("       Hunyuan3D 2.1 Houdini Plugin Installer             ")
    print("==========================================================")
    
    # Get the absolute path of this repository's houdini_plugin folder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.join(current_dir, "houdini_plugin")
    
    # Format with forward slashes for Houdini compatibility
    plugin_dir_clean = plugin_dir.replace("\\", "/")
    
    if not os.path.exists(plugin_dir):
        print(f"Error: Could not locate plugin directory at {plugin_dir}")
        print("Please run this script from the root of the Hunyuan3D-2.1 repository.")
        sys.exit(1)
        
    print(f"Found Houdini Plugin source: {plugin_dir_clean}")
    
    # Compile HDA
    compile_hda(current_dir, plugin_dir)
    
    documents_dirs = get_documents_dirs()
    if not documents_dirs:
        print("Error: Could not find any Documents directory.")
        print("Please manually copy the 'hunyuan3d.json' template from 'houdini_plugin/packages' to your Houdini packages directory.")
        sys.exit(1)
        
    houdini_folders = []
    for doc_dir in documents_dirs:
        # Search for folders like C:/Users/Name/Documents/houdini20.0, C:/Users/Name/Documents/houdini20.5
        pattern = os.path.join(doc_dir, "houdini*")
        found = glob.glob(pattern)
        for path in found:
            # Verify it's a directory and contains version numbers (like houdini20.5)
            if os.path.isdir(path) and any(char.isdigit() for char in os.path.basename(path)):
                if path not in houdini_folders:
                    houdini_folders.append(path)
                
    if not houdini_folders:
        print("\nNo active Houdini user directories detected (e.g. C:/Users/Name/Documents/houdini20.5).")
        # Try to locate the default documents folder and guess a path.
        fallback_dir = os.path.join(documents_dirs[0], "houdini20.5")
        print(f"Defaulting setup for: {fallback_dir}")
        houdini_folders.append(fallback_dir)
        
    installed_count = 0
    for houdini_path in houdini_folders:
        houdini_path = os.path.abspath(houdini_path)
        packages_dir = os.path.join(houdini_path, "packages")
        
        # Create packages directory if it doesn't exist
        os.makedirs(packages_dir, exist_ok=True)
        
        json_path = os.path.join(packages_dir, "hunyuan3d.json")
        
        # Package structure content
        package_data = {
            "path": plugin_dir_clean
        }
        
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(package_data, f, indent=4)
            print(f"\n[SUCCESS] Installed plugin package configuration for: {os.path.basename(houdini_path)}")
            print(f"          Package File: {json_path}")
            installed_count += 1
        except Exception as e:
            print(f"\n[ERROR] Failed to write package for {houdini_path}: {e}")
            
    if installed_count > 0:
        print("\n==========================================================")
        print("                 INSTALLATION COMPLETE!                    ")
        print("==========================================================")
        print("Instructions:")
        print("1. Launch Houdini.")
        print("2. You will find a new shelf tab named 'Hunyuan3D'.")
        print("   (If it does not show up, click the '+' icon next to your shelves,")
        print("    choose 'Shelves' -> check 'Hunyuan3D' to enable it).")
        print("3. Click the 'Hunyuan3D 2.1' button on the shelf to launch the tool.")
        print("4. Make sure your Hunyuan3D API Server is running (use the 'Start Server'")
        print("   button in the tool UI, or run start_api_server.bat).")
        print("==========================================================")
    else:
        print("\nInstallation failed. Could not write package files.")

if __name__ == "__main__":
    main()

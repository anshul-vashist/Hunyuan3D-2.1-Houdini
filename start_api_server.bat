@echo off
:: Change directory to the folder where this batch file is located
cd /d "%~dp0"

:: Clear Python environment variables to prevent pollution when started from Houdini
set PYTHONPATH=
set PYTHONHOME=

title Hunyuan3D 2.1 API Server
echo Starting Hunyuan3D 2.1 API Server...
echo Environment: hunyuan3d (Python 3.10)
echo Working Directory: %CD%
echo VRAM Mode: Low VRAM (recommended for <= 16GB VRAM)
echo.

:: Disable symlinks in Hugging Face Hub to prevent WinError 1314 (requires Admin/Dev Mode)
set HF_HUB_DISABLE_SYMLINKS=1

:: Run the server using absolute paths to avoid working directory mismatches
"C:\Users\Anshul\anaconda3\envs\hunyuan3d\python.exe" "E:\#AI#\Hunyuan 3d 2.1\api_server.py" --port 8081 --low_vram_mode

if %errorlevel% neq 0 (
    echo.
    echo Server crashed or failed to start.
    pause
)

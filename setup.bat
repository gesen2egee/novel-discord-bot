@echo off & chcp 65001 >nul
echo [Setup] Creating Python Virtual Environment (venv)...
if not exist "venv" (
    python -m venv venv
    if errorlevel 1 (
        echo [Error] Failed to create virtual environment. Please ensure Python is installed and added to PATH.
        pause
        exit /b 1
    )
)

echo [Setup] Installing dependencies from requirements.txt...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [Error] Failed to install dependencies.
    pause
    exit /b 1
)

echo [Success] Environment setup completed successfully!
pause

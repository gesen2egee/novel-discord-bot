@echo off & chcp 65001 >nul
echo [Update] Updating dependencies from requirements.txt...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    pip install --upgrade -r requirements.txt
    if errorlevel 1 (
        echo [Error] Failed to update dependencies.
        pause
        exit /b 1
    )
    echo [Success] Dependencies updated successfully!
) else (
    echo [Notice] Virtual environment not found. Please run setup.bat first.
)
pause

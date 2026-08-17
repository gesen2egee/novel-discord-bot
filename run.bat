@echo off & chcp 65001 >nul
if not exist "venv\Scripts\python.exe" (
    echo [Notice] Virtual environment not found. Running setup first...
    call setup.bat
)

echo [Start] Activating virtual environment and starting Discord Bot...
call venv\Scripts\activate.bat
python bot.py
if errorlevel 1 (
    echo [Error] Bot stopped with an error.
    pause
)
pause

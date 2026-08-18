@echo off
chcp 65001 >nul
title Discord Channel History Exporter

echo ======================================================
echo   Discord Channel History Exporter
echo ======================================================

if not exist "venv\Scripts\python.exe" (
    echo [Notice] Virtual environment not found. Running setup first...
    call setup.bat
)

echo [Start] Activating venv and running export tool...
call venv\Scripts\activate.bat
python export_channel.py
if errorlevel 1 (
    echo [Error] Export failed or stopped with an error.
    pause
)

pause

@echo off & chcp 65001 >nul
title Discord 頻道歷史訊息匯出工具

echo ======================================================
echo   Discord 頻道歷史訊息與圖片匯出工具
echo ======================================================

if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe export_channel.py
) else (
    python export_channel.py
)

pause

@echo off
title Pokemon Card Bot — Updater
echo.
echo  =======================================
echo   Pokemon Card Bot Updater
echo  =======================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python not found. Cannot run the updater.
    echo.
    pause
    exit /b 1
)

:: Run the updater
python update.py

@echo off
title Pokemon Card Bot — Installer
echo.
echo  =======================================
echo   Pokemon Card Bot Installer
echo  =======================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python not found.
    echo  Download from https://python.org and try again.
    echo.
    pause
    exit /b 1
)

:: Run the installer
python installer.py
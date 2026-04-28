@echo off
title Pokemon Card Bot — Uninstaller
echo.
echo  =======================================
echo   Pokemon Card Bot Uninstaller
echo  =======================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python not found. Cannot run the uninstaller.
    echo  You can manually delete %%LOCALAPPDATA%%\PokemonCardBot
    echo.
    pause
    exit /b 1
)

:: Run the uninstaller
python uninstaller.py

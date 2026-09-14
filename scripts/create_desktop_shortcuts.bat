@echo off
title QX Platform Desktop Shortcuts Creator
echo =========================================================
echo  CREATING DESKTOP SHORTCUTS FOR QX PLATFORM
echo =========================================================
echo.

powershell -ExecutionPolicy Bypass -File "C:\Project\2026\scripts\create_desktop_shortcuts.ps1"

echo.
echo =========================================================
echo  DESKTOP SHORTCUTS CREATION COMPLETE!
echo =========================================================
timeout /t 3

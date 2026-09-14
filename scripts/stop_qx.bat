@echo off
title QX Platform Stopper
echo =========================================================
echo  STOPPING QX QUANTITATIVE PLATFORM SERVERS
echo =========================================================
echo.

echo Stopping FastAPI Backend on port 8510...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8510 ^| findstr LISTENING') do (
    echo Killing PID %%a
    taskkill /f /pid %%a >nul 2>&1
)

echo Stopping React Dashboard Frontend on port 5174...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5174 ^| findstr LISTENING') do (
    echo Killing PID %%a
    taskkill /f /pid %%a >nul 2>&1
)

echo.
echo =========================================================
echo  ALL QX PLATFORM SERVERS HAVE BEEN STOPPED.
echo =========================================================
timeout /t 3

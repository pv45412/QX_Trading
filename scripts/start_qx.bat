@echo off
title QX Platform Starter
echo =========================================================
echo  STARTING QX QUANTITATIVE PLATFORM SERVERS & DATA SERVICES
echo =========================================================
echo.

cd /d "C:\Project\2026"

echo [1/3] Triggering Data Ingestion / Warmup Check...
".venv\Scripts\python.exe" -m qx.tools.run_preflight_checks

echo.
echo [2/3] Starting FastAPI Backend Engine (Port 8510)...
start "QX Backend Server (Port 8510)" cmd /k ""C:\Project\2026\.venv\Scripts\python.exe" -m uvicorn qx.interfaces.web:app --host 127.0.0.1 --port 8510"

echo.
echo [3/3] Starting React Dashboard Frontend (Port 5174)...
cd /d "C:\Project\2026\web"
start "QX React Dashboard (Port 5174)" cmd /k "npm run dev -- --port 5174"

echo.
echo =========================================================
echo  QX PLATFORM SERVERS LAUNCHED SUCCESSFULLY!
echo  - Dashboard URL: http://localhost:5174
echo  - Backend API:  http://127.0.0.1:8510
echo =========================================================
timeout /t 5

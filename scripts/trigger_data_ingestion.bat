@echo off
title QX Platform Data Ingestion Batch
echo =========================================================
echo  TRIGGERING QX AUTOMATED DATA INGESTION & CACHE WARMUP
echo =========================================================
echo.

cd /d "C:\Project\2026"

".venv\Scripts\python.exe" -m qx.automation.data_ingestion

echo.
echo =========================================================
echo  DATA INGESTION PIPELINE COMPLETED SUCCESSFULLY!
echo =========================================================
timeout /t 4

@echo off
title kikock Face Access Platform - Local Launcher

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "MODEL_DET=%ROOT_DIR%\backend\models\detector.onnx"
set "MODEL_FEAT=%ROOT_DIR%\backend\models\feature.onnx"

echo [1/3] Checking ONNX models...
if not exist "%MODEL_DET%" (
    echo Auto exporting ONNX models...
    cd /d "%ROOT_DIR%\backend"
    call mise exec -- uv run --group export python tools\export_onnx.py --sdk "D:\code\01_github_code\Open-Source-Face-Recognition-SDK"
)

echo [2/3] Starting Backend (FastAPI on http://localhost:8000)...
start "kikock-backend" /d "%ROOT_DIR%\backend" cmd.exe /k "set PYTHONPATH=. && mise exec -- uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo [3/3] Starting Frontend (Vite on http://localhost:3000)...
start "kikock-frontend" /d "%ROOT_DIR%\frontend" cmd.exe /k "mise exec -- npm run dev"

timeout /t 3 /nobreak >nul 2>&1
start http://localhost:3000

echo ==========================================================
echo Started!
echo Frontend: http://localhost:3000
echo Backend API Docs: http://localhost:8000/docs
echo Admin: admin / admin123456
echo ==========================================================
exit /b 0
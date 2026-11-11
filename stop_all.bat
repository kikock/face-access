@echo off
title kikock Face Access Platform - Local Stopper

echo Stopping backend (port 8000)...
for /f "tokens=5" %%a in ('netstat -ano -p tcp ^| findstr /r /c:":8000 *LISTENING"') do (
    if not "%%a"=="0" (
        taskkill /f /pid %%a >nul 2>&1
        echo Killed process %%a on port 8000
    )
)

echo Stopping frontend (port 3000)...
for /f "tokens=5" %%a in ('netstat -ano -p tcp ^| findstr /r /c:":3000 *LISTENING"') do (
    if not "%%a"=="0" (
        taskkill /f /pid %%a >nul 2>&1
        echo Killed process %%a on port 3000
    )
)

echo All services stopped.
timeout /t 2 >nul 2>&1
exit /b 0
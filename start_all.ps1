<#
.SYNOPSIS
    kikock 人脸识别服务平台 - 本地一键启动脚本 (PowerShell)
#>

$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $rootDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       kikock 人脸识别服务平台 - 本地一键启动" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. 检查模型文件
$modelDet = Join-Path $rootDir "backend\models\detector.onnx"
if (-not (Test-Path $modelDet)) {
    Write-Host "[提示] 正在自动导出 ONNX 模型文件..." -ForegroundColor Yellow
    Push-Location (Join-Path $rootDir "backend")
    mise exec -- uv run --group export python tools\export_onnx.py --sdk "D:\code\01_github_code\Open-Source-Face-Recognition-SDK"
    Pop-Location
}

# 2. 启动后端 FastAPI (兼容 Windows PowerShell 5.1，不使用 && 运算符)
Write-Host "[1/3] 正在启动后端 FastAPI 服务 (http://localhost:8000)..." -ForegroundColor Yellow
$backendCmd = "cd /d `"$rootDir\backend`" & set PYTHONPATH=. & uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "title kikock-后端服务 & $backendCmd"

# 3. 启动前端 Vite
Write-Host "[2/3] 正在启动前端 Vite 服务 (http://localhost:3000)..." -ForegroundColor Yellow
$frontendCmd = "cd /d `"$rootDir\frontend`" & mise exec -- npm run dev"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "title kikock-前端服务 & $frontendCmd"

# 4. 等待就绪并打开默认浏览器
Write-Host "[3/3] 等待服务预热并自动打开浏览器..." -ForegroundColor Yellow
Start-Sleep -Seconds 3
Start-Process "http://localhost:3000"

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "服务启动完成！" -ForegroundColor Green
Write-Host "- 前端页面: http://localhost:3000"
Write-Host "- 后端文档: http://localhost:8000/docs"
Write-Host "- 默认初始管理员: admin / admin123456"
Write-Host "==========================================================" -ForegroundColor Cyan

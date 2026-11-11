<#
.SYNOPSIS
    kikock 人脸识别服务平台 - 本地一键停止脚本 (PowerShell)
.DESCRIPTION
    彻底杀死占用 8000 (后端) 与 3000 (前端) 端口的所有本地开发进程
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "正在停止 kikock 人脸识别服务平台本地进程..." -ForegroundColor Yellow

$ports = @(8000, 3000)
foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conns) {
        $pids = $conns.OwningProcess | Select-Object -Unique
        foreach ($p in $pids) {
            try {
                Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
                Write-Host "已杀死占用端口 $port 的进程 (PID: $p)" -ForegroundColor Green
            } catch {}
        }
    } else {
        Write-Host "端口 $port 未被占用" -ForegroundColor Gray
    }
}

Write-Host "全部服务已停止！" -ForegroundColor Cyan


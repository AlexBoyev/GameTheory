<#
.SYNOPSIS
    Starts the Game Theory backend and frontend in two separate windows.

.DESCRIPTION
    Non-Docker development. Each server gets its own PowerShell window so logs
    stay readable and either can be restarted on its own.

.PARAMETER BackendPort
    Port for uvicorn. Change it if something else already owns 8000 (IIS,
    Apache/XAMPP, another dev server) - the frontend proxy follows automatically.

.PARAMETER NoFrontend
    Start only the backend.

.EXAMPLE
    .\scripts\dev.ps1
    .\scripts\dev.ps1 -BackendPort 8001
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [switch]$NoFrontend,
    [switch]$NoBackend
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Test-PortFree {
    param([int]$Port)
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        $owner = Get-Process -Id $listener[0].OwningProcess -ErrorAction SilentlyContinue
        Write-Warning "Port $Port is already in use by '$($owner.ProcessName)' (pid $($listener[0].OwningProcess))."
        Write-Warning "Re-run with -BackendPort <other> or stop that process first."
        return $false
    }
    return $true
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
}

if (-not $NoBackend) {
    if (-not (Test-PortFree -Port $BackendPort)) { exit 1 }

    Write-Host "Starting backend on http://localhost:$BackendPort ..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location '$backend'; `$host.UI.RawUI.WindowTitle = 'Game Theory backend'; uv run uvicorn app.main:app --reload --port $BackendPort"
    )
}

if (-not $NoFrontend) {
    if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
        Write-Host 'Installing frontend dependencies (first run)...' -ForegroundColor Cyan
        Push-Location $frontend
        npm install
        Pop-Location
    }

    Write-Host 'Starting frontend on http://localhost:5173 ...' -ForegroundColor Cyan
    $backendUrl = "http://localhost:$BackendPort"
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location '$frontend'; `$host.UI.RawUI.WindowTitle = 'Game Theory frontend'; `$env:VITE_BACKEND_URL = '$backendUrl'; npm run dev"
    )
}

Write-Host ''
Write-Host 'Open http://localhost:5173 once both windows report ready.' -ForegroundColor Green
Write-Host "API docs: http://localhost:$BackendPort/docs" -ForegroundColor Green

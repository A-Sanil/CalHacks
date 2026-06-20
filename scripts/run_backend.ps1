# Start the Aegis Route FastAPI solver backend on http://localhost:8000
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
if (-not (Test-Path .venv)) { python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt }
Write-Host "Starting solver backend on http://localhost:$Port ..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m uvicorn solver.api.app:app --host 0.0.0.0 --port $Port --reload

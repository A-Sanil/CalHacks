# Start the Aegis Route React dashboard (Vite) on http://localhost:5173
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..\frontend
if (-not (Test-Path node_modules)) { npm install }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "Starting dashboard on http://localhost:5173 (backend expected at http://localhost:8000)" -ForegroundColor Cyan
npm run dev

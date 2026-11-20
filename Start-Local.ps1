# Start the Windows single-computer application from this repository directory.
# Initial dependency installation requires internet; normal operation uses localhost.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path 'backend/.venv/Scripts/python.exe')) {
    python -m venv backend/.venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
    & backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
}
if (-not (Test-Path 'node_modules')) {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
}
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
# The caller may override the data root before launching. It must be writable.
if (-not $env:CAPTURE_DATA_DIR) { $env:CAPTURE_DATA_DIR = Join-Path $env:LOCALAPPDATA 'ClarityCapture/data' }
Write-Host "Open http://127.0.0.1:8000 in Chrome or Edge. Data: $env:CAPTURE_DATA_DIR"
# Keep this terminal running. Ctrl+C stops only this application's web server.
& backend/.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

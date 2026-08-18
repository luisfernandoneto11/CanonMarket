$ErrorActionPreference = "Stop"

Write-Host "Creating virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path ".venv")) {
    py -m venv .venv
}

Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Setup completed successfully." -ForegroundColor Green
Write-Host "Run: .\run_windows.ps1"

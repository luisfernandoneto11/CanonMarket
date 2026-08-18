$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Virtual environment not found. Run .\setup_windows.ps1 first."
}

& .\.venv\Scripts\python.exe -m pytest -q

# start.ps1
# Run this script from the project folder or by right-clicking -> Run with PowerShell.
# It activates .venv, loads simple KEY=VALUE entries from .env, and starts FastAPI.

$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "`n=== Kapso Issue Agent startup ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

# 1. Check virtual environment
$ActivateScript = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $ActivateScript)) {
    Write-Host "ERROR: .venv was not found. Create it first with: python -m venv .venv" -ForegroundColor Red
    exit 1
}

# 2. Check .env file
$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "ERROR: .env was not found. Copy .env.example to .env and fill in the required values first." -ForegroundColor Red
    exit 1
}

# 3. Activate the virtual environment
. $ActivateScript
Write-Host "Virtual environment activated." -ForegroundColor Green

# 4. Load simple KEY=VALUE entries from .env into this PowerShell process.
# Blank lines and lines beginning with # are ignored.
# Supports optional matching single or double quotes around values.
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line -split "=", 2
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()

        if ($key -match '^[A-Za-z_][A-Za-z0-9_]*$') {
            if (($value.Length -ge 2) -and
                (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                 ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }

            # Do not print secrets to the terminal.
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}
Write-Host ".env values loaded (values are not displayed)." -ForegroundColor Green

# 5. Start the FastAPI app. Keep this terminal open while the server runs.
Write-Host "`nStarting FastAPI at http://127.0.0.1:8000 ..." -ForegroundColor Cyan
python -m uvicorn app.main:app --reload

# NETZWACHE - Startskript für Windows / PowerShell
# Aufruf:  .\start-windows.ps1          (Docker)
#          .\start-windows.ps1 -Dev     (ohne Docker, SQLite + Vite)

param([switch]$Dev)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[+] .env aus .env.example erzeugt" -ForegroundColor Green
}

if ($Dev) {
    Write-Host "[*] Entwicklungsmodus (SQLite, kein Docker)" -ForegroundColor Cyan

    if (-not (Test-Path "backend\.venv")) {
        Write-Host "[*] Lege Python-venv an ..."
        python -m venv backend\.venv
        & backend\.venv\Scripts\pip.exe install -r backend\requirements.txt
    }
    if (-not (Test-Path "frontend\node_modules")) {
        Write-Host "[*] Installiere Frontend-Abhängigkeiten ..."
        Push-Location frontend; npm install; Pop-Location
    }

    $env:DATABASE_URL = "sqlite+aiosqlite:///./netzwache.db"
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$PSScriptRoot\backend'; `$env:DATABASE_URL='sqlite+aiosqlite:///./netzwache.db'; .\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000"
    )
    Start-Sleep -Seconds 4
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm run dev"
    )
    Start-Sleep -Seconds 4
    Start-Process "http://localhost:5173"
    Write-Host "[OK] Dashboard: http://localhost:5173   API-Doku: http://localhost:8000/docs" -ForegroundColor Green
}
else {
    Write-Host "[*] Starte Docker-Stack ..." -ForegroundColor Cyan
    docker compose up --build -d
    Start-Sleep -Seconds 6
    Start-Process "http://localhost:8080"
    Write-Host "[OK] Dashboard: http://localhost:8080   API-Doku: http://localhost:8000/docs" -ForegroundColor Green
    Write-Host "    Logs:   docker compose logs -f backend"
    Write-Host "    Stopp:  docker compose down"
}

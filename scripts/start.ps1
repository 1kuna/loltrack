param([switch]$Prod)
$ErrorActionPreference = "Stop"

if (-not (Test-Path .venv)) { python -m venv .venv }
./.venv/Scripts/python -m pip install -U pip
./.venv/Scripts/pip install -e .
./.venv/Scripts/pip install -e backend

if (Test-Path frontend/package.json) {
  if (-not (Test-Path frontend/node_modules)) {
    pushd frontend
    if (Test-Path package-lock.json) { npm ci } else { npm install }
    popd
  }
} else {
  Write-Host "No frontend found (frontend/). Backend will run without UI."
}

$env:PORT = $env:PORT -as [string]
if (-not $env:PORT) { $env:PORT = "8787" }

if ($Prod) {
  if (Test-Path frontend/package.json) { pushd frontend; npm run build; popd }
  Start-Process "http://127.0.0.1:$($env:PORT)/" | Out-Null
  ./.venv/Scripts/uvicorn server.app:app --host 127.0.0.1 --port $env:PORT
} else {
  if (Test-Path frontend/package.json) {
    $p = Start-Process powershell -ArgumentList "-NoLogo -NoProfile -Command cd frontend; npm run dev" -PassThru
    $p.Id | Out-File -FilePath ./.vite.pid
  }
  ./.venv/Scripts/uvicorn server.app:app --reload --host 127.0.0.1 --port $env:PORT
}

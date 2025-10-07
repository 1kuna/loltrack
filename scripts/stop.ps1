if (Test-Path ./.vite.pid) {
  $p = Get-Content ./.vite.pid | Select-Object -First 1
  Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
  Remove-Item ./.vite.pid -ErrorAction SilentlyContinue
}
Get-Process -Name uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force


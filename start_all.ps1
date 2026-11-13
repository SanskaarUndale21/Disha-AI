# Disha AI launcher: starts the API, the admin panel, the citizen portal and the feed panel, then keeps them alive.
# Usage:  powershell -ExecutionPolicy Bypass -File start_all.ps1        (stop with stop_all.ps1)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null

function Port-Up($port) { return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }

function Start-Svc($name, $port) {
    if (Port-Up $port) { return }
    Write-Host "starting $name on :$port"
    switch ($name) {
        "api"     { Start-Process $py -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory "$root\backend" -RedirectStandardOutput "$root\logs\api.log" -RedirectStandardError "$root\logs\api.err.log" -WindowStyle Hidden }
        "admin"   { Start-Process cmd -ArgumentList "/c","cd /d $root\frontend && npx vite preview --host 0.0.0.0 --port 5173 > $root\logs\admin.log 2>&1" -WindowStyle Hidden }
        "citizen" { Start-Process $py -ArgumentList "$root\citizen_web\serve.py" -RedirectStandardOutput "$root\logs\citizen.log" -RedirectStandardError "$root\logs\citizen.err.log" -WindowStyle Hidden }
        "feed"    { Start-Process $py -ArgumentList "$root\feed_panel\serve.py" -RedirectStandardOutput "$root\logs\feed.log" -RedirectStandardError "$root\logs\feed.err.log" -WindowStyle Hidden }
    }
}

# build the admin panel once if missing
if (-not (Test-Path "$root\frontend\dist\index.html")) { Write-Host "building admin panel"; Push-Location "$root\frontend"; npx vite build; Pop-Location }

$services = @(@("api",8000), @("admin",5173), @("citizen",5174), @("feed",5175))
foreach ($s in $services) { Start-Svc $s[0] $s[1] }
Start-Sleep 20
Write-Host ""
Write-Host "Disha AI is running:"
Write-Host "  Admin panel     http://localhost:5173"
Write-Host "  Citizen portal  http://localhost:5174"
Write-Host "  Feed panel      http://localhost:5175"
Write-Host "  Map             http://localhost:8000/map"
Write-Host "  API docs        http://localhost:8000/docs"
Write-Host "Watchdog active: crashed services restart automatically. Press Ctrl+C to leave it (services keep running)."
while ($true) {
    Start-Sleep 30
    foreach ($s in $services) { Start-Svc $s[0] $s[1] }
}

# Stops everything started by start_all.ps1
foreach ($port in 8000,5173,5174,5175) {
    $p = (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess
    if ($p) { Stop-Process -Id $p -Force; Write-Host "stopped :$port" }
}

# Beendet alle Prozesse, die Port 8000 halten (inkl. Uvicorn-Multiprocessing-Kinder)
$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($p in ($conns | Select-Object -ExpandProperty OwningProcess -Unique)) {
  if ($p -gt 0) { Write-Host ("kill port-owner " + $p); Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
}
# Python-Prozesse: direkter Match ODER Multiprocessing-Kinder (Elber tot / SoftLabel-Server)
$live = (Get-Process -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
  $_.CommandLine -match 'run\.py|uvicorn app\.main' -or
  ($_.CommandLine -match 'multiprocessing-fork' -and ($_.ParentProcessId -notin $live))
} | ForEach-Object {
  Write-Host ("kill " + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 1
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
  Write-Host "WARNUNG: Port 8000 noch belegt" } else { Write-Host "port 8000 frei" }

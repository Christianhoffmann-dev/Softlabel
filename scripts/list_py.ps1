Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object {
  Write-Host ("{0} :: {1}" -f $_.ProcessId, $_.CommandLine)
}

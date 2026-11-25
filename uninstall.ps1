# Stops League Limiter and removes it from startup. Your history stays in %LOCALAPPDATA%\LeagueLimiter.
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'League Limiter.lnk'
if (Test-Path $lnk) { Remove-Item $lnk -Confirm:$false }
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*limiter.pyw*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
Write-Host 'League Limiter stopped and removed from startup.'

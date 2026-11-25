# Installs League Limiter: starts it now and at every logon (Startup folder shortcut).
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'limiter.pyw'

# Find pythonw.exe (prefer the py launcher's newest Python)
$pythonw = $null
try {
    $exe = (& py -3 -c "import sys; print(sys.executable)") 2>$null
    if ($exe) { $pythonw = Join-Path (Split-Path $exe) 'pythonw.exe' }
} catch {}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $pythonw = $cmd.Source }
}
if (-not $pythonw -or -not (Test-Path $pythonw)) { throw 'pythonw.exe not found. Install Python 3 from python.org.' }

$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup 'League Limiter.lnk'
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = $pythonw
$s.Arguments = "`"$script`""
$s.WorkingDirectory = $PSScriptRoot
$s.Description = 'League Limiter'
$s.Save()

Start-Process -FilePath $pythonw -ArgumentList "`"$script`"" -WorkingDirectory $PSScriptRoot
Write-Host "Installed. Shortcut: $lnk"
Write-Host "League Limiter is running in the background."

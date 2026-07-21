$ErrorActionPreference = "Stop"

$Binary = "jtunnel"
$InstallDir = Join-Path $env:LOCALAPPDATA "jtunnel"
$InstallPath = Join-Path $InstallDir "$Binary.exe"
$ConfigDir = Join-Path $env:USERPROFILE ".config\jtunnel"

if (Test-Path $InstallPath) {
    Write-Host "Removing $InstallPath..."
    Remove-Item -Force $InstallPath
} else {
    Write-Host "Binary not found at $InstallPath (already removed?)."
}

if ((Test-Path $InstallDir) -and -not (Get-ChildItem -Force $InstallDir | Select-Object -First 1)) {
    Remove-Item -Force $InstallDir
}

if (Test-Path $ConfigDir) {
    Write-Host "Removing config $ConfigDir..."
    Remove-Item -Recurse -Force $ConfigDir
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $parts = $userPath -split ";" | Where-Object { $_ -ne "" -and $_ -ne $InstallDir }
    $newPath = $parts -join ";"
    if ($newPath -ne $userPath) {
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "Removed $InstallDir from user PATH."
    }
}

Write-Host ""
Write-Host "JTunnel uninstalled."

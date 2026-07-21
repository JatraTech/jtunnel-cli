$ErrorActionPreference = "Stop"

$Repo = "JatraTech/jtunnel-cli"
$Binary = "jtunnel"
$InstallDir = Join-Path $env:LOCALAPPDATA "jtunnel"
$InstallPath = Join-Path $InstallDir "$Binary.exe"

$arch = switch ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture) {
    "X64" { "amd64" }
    "Arm64" { "arm64" }
    default {
        Write-Error "Unsupported architecture: $_"
        exit 1
    }
}

$File = "$Binary-windows-$arch.exe"
$Url = "https://github.com/$Repo/releases/latest/download/$File"

Write-Host "Downloading $File..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) $File
try {
    Invoke-WebRequest -Uri $Url -OutFile $tmp -UseBasicParsing
    Move-Item -Force $tmp $InstallPath
} finally {
    if (Test-Path $tmp) { Remove-Item -Force $tmp }
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
$pathParts = $userPath -split ";" | Where-Object { $_ -ne "" }
if ($pathParts -notcontains $InstallDir) {
    $newPath = if ($userPath.TrimEnd(";")) { "$($userPath.TrimEnd(';'));$InstallDir" } else { $InstallDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$env:Path;$InstallDir"
    Write-Host "Added $InstallDir to user PATH."
}

Write-Host ""
Write-Host "JTunnel installed successfully!"
Write-Host "  $InstallPath"
Write-Host ""
Write-Host "Open a new terminal, then run:"
Write-Host "  jtunnel --help"

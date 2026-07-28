$ErrorActionPreference = "Stop"

$Repo = "JatraTech/jtunnel-cli"
$Binary = "jtunnel"
$InstallDir = Join-Path $env:LOCALAPPDATA "jtunnel"
$InstallPath = Join-Path $InstallDir "$Binary.exe"
$FirewallScriptUrl = "https://raw.githubusercontent.com/$Repo/main/scripts/windows-firewall.ps1"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Add-JtunnelFirewallRule {
    param([string]$ProgramPath)

    $fwTmp = Join-Path ([System.IO.Path]::GetTempPath()) "jtunnel-windows-firewall.ps1"
    try {
        Invoke-WebRequest -Uri $FirewallScriptUrl -OutFile $fwTmp -UseBasicParsing
        if (Test-IsAdmin) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $fwTmp -Action Add -ProgramPath $ProgramPath
            return $LASTEXITCODE -eq 0
        }

        Write-Host "Requesting Administrator approval to add a Windows Firewall rule..."
        $argList = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$fwTmp`"",
            "-Action", "Add",
            "-ProgramPath", "`"$ProgramPath`""
        )
        $proc = Start-Process -FilePath "powershell" -Verb RunAs -Wait -PassThru -ArgumentList $argList
        return ($proc.ExitCode -eq 0)
    } catch {
        return $false
    } finally {
        if (Test-Path $fwTmp) { Remove-Item -Force $fwTmp -ErrorAction SilentlyContinue }
    }
}

# Prefer native OS arch (handles 32-bit PowerShell on 64-bit Windows).
$rawArch = if ($env:PROCESSOR_ARCHITEW6432) {
    $env:PROCESSOR_ARCHITEW6432
} else {
    $env:PROCESSOR_ARCHITECTURE
}

$arch = switch ($rawArch.ToUpperInvariant()) {
    "AMD64" { "amd64" }
    "ARM64" { "arm64" }
    default {
        Write-Error "Unsupported architecture: $rawArch"
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
Write-Host "Configuring Windows Firewall..."
$fwOk = Add-JtunnelFirewallRule -ProgramPath $InstallPath
if (-not $fwOk) {
    Write-Host ""
    Write-Host "Warning: Could not add the Windows Firewall rule (UAC declined or error)."
    Write-Host "JT Tunnel is installed, but outbound connections may be blocked."
    Write-Host "Run PowerShell as Administrator and execute:"
    Write-Host "  irm https://raw.githubusercontent.com/$Repo/main/scripts/windows-firewall.ps1 -OutFile `$env:TEMP\jtunnel-fw.ps1"
    Write-Host "  powershell -ExecutionPolicy Bypass -File `$env:TEMP\jtunnel-fw.ps1 -Action Add -ProgramPath `"$InstallPath`""
    Write-Host "Or run: jtunnel doctor"
}

Write-Host ""
Write-Host "JTunnel installed successfully!"
Write-Host "  $InstallPath"
Write-Host ""
Write-Host "Open a new terminal, then run:"
Write-Host "  jtunnel --help"
Write-Host "  jtunnel doctor"

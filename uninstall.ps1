$ErrorActionPreference = "Stop"

$Repo = "JatraTech/jtunnel-cli"
$Binary = "jtunnel"
$InstallDir = Join-Path $env:LOCALAPPDATA "jtunnel"
$InstallPath = Join-Path $InstallDir "$Binary.exe"
$ConfigDir = Join-Path $env:USERPROFILE ".config\jtunnel"
$FirewallScriptUrl = "https://raw.githubusercontent.com/$Repo/main/scripts/windows-firewall.ps1"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Remove-JtunnelFirewallRule {
    param([string]$ProgramPath)

    $fwTmp = Join-Path ([System.IO.Path]::GetTempPath()) "jtunnel-windows-firewall.ps1"
    try {
        Invoke-WebRequest -Uri $FirewallScriptUrl -OutFile $fwTmp -UseBasicParsing
        if (Test-IsAdmin) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $fwTmp -Action Remove -ProgramPath $ProgramPath
            return $LASTEXITCODE -eq 0
        }

        Write-Host "Requesting Administrator approval to remove the Windows Firewall rule..."
        $argList = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$fwTmp`"",
            "-Action", "Remove",
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

Write-Host "Removing Windows Firewall rule..."
$fwOk = Remove-JtunnelFirewallRule -ProgramPath $InstallPath
if (-not $fwOk) {
    Write-Host "Warning: Could not remove the firewall rule (UAC declined or not present)."
    Write-Host "You can remove it manually in Windows Defender Firewall, or run as Administrator:"
    Write-Host "  irm https://raw.githubusercontent.com/$Repo/main/scripts/windows-firewall.ps1 -OutFile `$env:TEMP\jtunnel-fw.ps1"
    Write-Host "  powershell -ExecutionPolicy Bypass -File `$env:TEMP\jtunnel-fw.ps1 -Action Remove"
}

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

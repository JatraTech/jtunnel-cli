#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Add or remove the JT Tunnel Windows Firewall outbound allow rule.

.PARAMETER Action
  Add or Remove

.PARAMETER ProgramPath
  Full path to jtunnel.exe (defaults to %LOCALAPPDATA%\jtunnel\jtunnel.exe)
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Add", "Remove")]
    [string]$Action,

    [Parameter(Mandatory = $false)]
    [string]$ProgramPath = ""
)

$ErrorActionPreference = "Stop"

$RuleName = "JT Tunnel"

if (-not $ProgramPath) {
    $ProgramPath = Join-Path $env:LOCALAPPDATA "jtunnel\jtunnel.exe"
}

$ProgramPath = [System.IO.Path]::GetFullPath($ProgramPath)

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Error "Administrator privileges required. Run PowerShell as Administrator."
    exit 1
}

$existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue

if ($Action -eq "Add") {
    if (-not (Test-Path -LiteralPath $ProgramPath)) {
        Write-Error "Program not found: $ProgramPath"
        exit 1
    }

    if ($existing) {
        $apps = $existing | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue
        $same = $false
        foreach ($app in $apps) {
            if ($app.Program -and ([System.IO.Path]::GetFullPath($app.Program) -eq $ProgramPath)) {
                $same = $true
                break
            }
        }
        if ($same) {
            Write-Host "Firewall rule '$RuleName' already exists for $ProgramPath"
            exit 0
        }
        Remove-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
    }

    New-NetFirewallRule `
        -DisplayName $RuleName `
        -Direction Outbound `
        -Program $ProgramPath `
        -Action Allow `
        -Profile Domain,Private,Public `
        -Description "Allow JT Tunnel CLI outbound connections to the tunnel edge" | Out-Null

    Write-Host "Firewall rule added for JT Tunnel."
    Write-Host "  Program: $ProgramPath"
    exit 0
}

# Remove
if ($existing) {
    Remove-NetFirewallRule -DisplayName $RuleName
    Write-Host "Firewall rule '$RuleName' removed."
} else {
    Write-Host "Firewall rule '$RuleName' not found (already removed?)."
}
exit 0

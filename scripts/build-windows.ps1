$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$arch = switch ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture) {
    "X64" { "amd64" }
    "Arm64" { "arm64" }
    default { $_.ToString().ToLowerInvariant() }
}

$artifact = "jtunnel-windows-${arch}.exe"

uv sync --extra dev
uv run pyinstaller --clean jtunnel.spec

Move-Item -Force dist\jtunnel.exe "dist\${artifact}"

Write-Host "Built: dist\${artifact}"
Write-Host "Put dist\${artifact} on PATH, or run it directly."

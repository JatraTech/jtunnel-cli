$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$rawArch = if ($env:PROCESSOR_ARCHITEW6432) {
    $env:PROCESSOR_ARCHITEW6432
} else {
    $env:PROCESSOR_ARCHITECTURE
}

$arch = switch ($rawArch.ToUpperInvariant()) {
    "AMD64" { "amd64" }
    "ARM64" { "arm64" }
    default { $rawArch.ToLowerInvariant() }
}

$artifact = "jtunnel-windows-${arch}.exe"

uv sync --extra dev
uv run pyinstaller --clean jtunnel.spec

Move-Item -Force dist\jtunnel.exe "dist\${artifact}"

Write-Host "Built: dist\${artifact}"
Write-Host "Put dist\${artifact} on PATH, or run it directly."

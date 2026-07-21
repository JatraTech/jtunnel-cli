$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

uv sync --extra dev
uv run pyinstaller --clean jtunnel.spec

Write-Host "Built: dist\jtunnel.exe"
Write-Host "Put dist\jtunnel.exe on PATH, or run it directly."

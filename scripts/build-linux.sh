#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv sync --extra dev
uv run pyinstaller --clean jtunnel.spec

echo "Built: dist/jtunnel"
echo "Install: sudo install -m 755 dist/jtunnel /usr/local/bin/jtunnel"

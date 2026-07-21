#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

case "$(uname -m)" in
  x86_64|amd64) arch="amd64" ;;
  aarch64|arm64) arch="arm64" ;;
  *) arch="$(uname -m)" ;;
esac

artifact="jtunnel-linux-${arch}"

uv sync --extra dev
uv run pyinstaller --clean jtunnel.spec

mv -f dist/jtunnel "dist/${artifact}"

echo "Built: dist/${artifact}"
echo "Install: sudo install -m 755 dist/${artifact} /usr/local/bin/jtunnel"

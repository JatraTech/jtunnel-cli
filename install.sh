#!/usr/bin/env bash
set -euo pipefail

REPO="JatraTech/jtunnel"
BINARY="jtunnel"

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux) OS="linux" ;;
  Darwin) OS="macos" ;;
  *)
    echo "Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

case "$ARCH" in
  x86_64|amd64) ARCH="amd64" ;;
  arm64|aarch64) ARCH="arm64" ;;
  *)
    echo "Unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

FILE="${BINARY}-${OS}-${ARCH}"
URL="https://github.com/${REPO}/releases/latest/download/${FILE}"

echo "Downloading ${FILE}..."

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

curl -fsSL "$URL" -o "$TMP"
chmod +x "$TMP"

INSTALL_DIR="/usr/local/bin"
if [[ ! -w "$INSTALL_DIR" ]]; then
  echo "Installing to ${INSTALL_DIR}/${BINARY} (sudo)..."
  sudo mv "$TMP" "${INSTALL_DIR}/${BINARY}"
else
  echo "Installing to ${INSTALL_DIR}/${BINARY}..."
  mv "$TMP" "${INSTALL_DIR}/${BINARY}"
fi
trap - EXIT

echo
echo "JTunnel installed successfully!"
echo
echo "Run:"
echo "  jtunnel --help"

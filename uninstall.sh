#!/usr/bin/env bash
set -euo pipefail

BINARY="jtunnel"
INSTALL_PATH="/usr/local/bin/${BINARY}"
CONFIG_DIR="${JTUNNEL_CONFIG_DIR:-${HOME}/.config/jtunnel}"

if [[ -e "$INSTALL_PATH" ]] || command -v "$BINARY" >/dev/null 2>&1; then
  if [[ -e "$INSTALL_PATH" ]]; then
    TARGET="$INSTALL_PATH"
  else
    TARGET="$(command -v "$BINARY")"
  fi

  if [[ -w "$(dirname "$TARGET")" ]]; then
    echo "Removing ${TARGET}..."
    rm -f "$TARGET"
  else
    echo "Removing ${TARGET} (sudo)..."
    sudo rm -f "$TARGET"
  fi
else
  echo "Binary not found at ${INSTALL_PATH} (already removed?)."
fi

if [[ -d "$CONFIG_DIR" ]]; then
  echo "Removing config ${CONFIG_DIR}..."
  rm -rf "$CONFIG_DIR"
fi

echo
echo "JTunnel uninstalled."

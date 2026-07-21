"""PyInstaller entry point (absolute imports so the package freezes correctly)."""

from jtunnel.cli import app

if __name__ == "__main__":
    app()

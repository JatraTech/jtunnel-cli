# JT Tunnel CLI

Expose local services through JT Tunnel. Run `jtunnel` for an interactive menu (recommended), or use commands for scripts/CI.

The interactive UI is plain ASCII with high-contrast ANSI colors (readable on Ubuntu, Windows CMD, and PowerShell).

## Install

**Linux / macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/JatraTech/jtunnel-cli/main/install.sh | bash
```

Installs to `/usr/local/bin/jtunnel`.

**Windows** (PowerShell)

```powershell
irm https://raw.githubusercontent.com/JatraTech/jtunnel-cli/main/install.ps1 | iex
```

Installs to `%LOCALAPPDATA%\jtunnel\jtunnel.exe` and adds that folder to your user `PATH`.

## Uninstall

**Linux / macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/JatraTech/jtunnel-cli/main/uninstall.sh | bash
```

Removes `/usr/local/bin/jtunnel` and `~/.config/jtunnel`.

**Windows** (PowerShell)

```powershell
irm https://raw.githubusercontent.com/JatraTech/jtunnel-cli/main/uninstall.ps1 | iex
```

Removes `%LOCALAPPDATA%\jtunnel` and `%USERPROFILE%\.config\jtunnel`.

## Quick start

```bash
jtunnel          # interactive menu
```

1. Choose **Login** — approve the device code in your browser  
2. Start your app locally (e.g. `npm run dev` on `:5173`)  
3. Choose **Expose** — enter a service label and local port (or reuse a saved tunnel)  
4. Share the printed public URL (e.g. `https://jtunnel.new901.io:9001`)

Ctrl+C disconnects the tunnel and returns to the menu.

## Interactive menu

Run bare `jtunnel` in a terminal. The header shows sign-in state, your allocated port range, host, and default tunnel (`*`).

| Item | Behavior |
|------|----------|
| **Expose** | If a default saved tunnel exists, starts it immediately. Otherwise: choose a saved tunnel, or configure a new one (label + local port). |
| **Expose multiple** | Start all saved (up to 3), pick which saved to include, or configure new services interactively. |
| **List tunnels** | List of saved tunnels. Then: **Start** one, **Set default**, or **Back**. |
| **Login** / **Logout** | Device-code browser sign-in, or clear local credentials and tunnel state. |
| **Quit** | Exit the menu. |

Saved tunnels remember public port mappings (sticky by service name). The last started service becomes the **default** for quick Expose next time (`~/.config/jtunnel/preferences.json`).

Max concurrent tunnels: up to **3**, within your admin-assigned port block.

## Commands (scripts / CI)

When stdin is not a TTY, the CLI does not open the menu and does not prompt.

```bash
jtunnel login
jtunnel expose -p 5173              # label defaults to "default"
jtunnel expose api -p 8000
jtunnel expose --wizard             # multi-service (TTY: menu; non-TTY: prompts)
jtunnel list
jtunnel status
jtunnel logout
```

Interactive TTY shortcuts:

```bash
jtunnel expose              # same as menu Expose (default saved or prompts)
jtunnel expose --wizard     # same as menu Expose multiple
```

Local port when `-p` is omitted:

1. `.jtunnel.toml` → `port` key  
2. Default `3000`

## Configuration

Endpoints are hardcoded in the CLI (`jtunnel/config.py`):

| Setting | Value |
|---------|-------|
| API base | `https://admin.new901.io` |
| Tunnel host | `wss://jtunnel.new901.io` |
| Public host | `jtunnel.new901.io` |
| Config dir | `~/.config/jtunnel` |

After login, port range and host also come from `tunnel.json` or claims in the device token.

Local files under the config dir:

| File | Purpose |
|------|---------|
| `device.jwt` | Device auth token |
| `tunnel.json` | Allocated port block + host |
| `tunnels.json` | Saved tunnel mappings (name → public/local ports) |
| `preferences.json` | Default service for quick Expose |

## Binary builds

Build a standalone binary with PyInstaller on the same OS you target. Artifacts match GitHub Release names.

### Ubuntu / WSL

```bash
./scripts/build-linux.sh
sudo install -m 755 dist/jtunnel-linux-amd64 /usr/local/bin/jtunnel
```

### Windows

```powershell
.\scripts\build-windows.ps1
# put dist\jtunnel-windows-amd64.exe on PATH
```
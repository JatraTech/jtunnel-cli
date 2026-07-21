# JT Tunnel CLI

Expose local services through JT Tunnel. Run `jtunnel` for an interactive menu (recommended), or use commands for scripts/CI.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/JatraTech/jtunnel/main/install.sh | bash
```

Installs the latest release binary to `/usr/local/bin/jtunnel`.

Windows: download `jtunnel-windows-amd64.exe` from [Releases](https://github.com/JatraTech/jtunnel/releases) and put it on your `PATH`.

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

Run bare `jtunnel` in a terminal. The header shows sign-in state, your allocated port range, host, and default tunnel (★).

| Item | Behavior |
|------|----------|
| **Expose** | If a default saved tunnel exists, starts it immediately. Otherwise: choose a saved tunnel, or configure a new one (label + local port). |
| **Expose multiple** | Start all saved (up to 3), pick which saved to include, or configure new services interactively. |
| **List tunnels** | Table of saved tunnels. Then: **Start** one, **Set default**, or **Back**. |
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

| Variable | Default | Purpose |
|----------|---------|---------|
| `JTUNNEL_API_BASE` | `https://admin.new901.io` | Django API base URL |
| `JTUNNEL_HOST` | `wss://jtunnel.new901.io` | Go control WebSocket URL |
| `JTUNNEL_PUBLIC_HOST` | `jtunnel.new901.io` | Public tunnel hostname |
| `JTUNNEL_CONFIG_DIR` | `~/.config/jtunnel` | Local config directory |

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

Release asset names: `jtunnel-linux-amd64`, `jtunnel-linux-arm64`, `jtunnel-macos-amd64`, `jtunnel-macos-arm64`, `jtunnel-windows-amd64.exe`.

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

Install may prompt once for **Administrator (UAC)** approval to add a Windows Firewall **outbound** allow rule for `jtunnel.exe`. JT Tunnel is a client (it does not listen on a local port), so Windows will not show the usual public/private network popup — the install script adds the rule explicitly.

If you decline UAC, install still succeeds. Add the rule later with:

```powershell
jtunnel doctor --fix-firewall
```

> Note: Loopback (`127.0.0.1`) is not blocked by Windows Firewall. If the public URL returns connection refused after the tunnel is connected, start your local app and pass the correct port (`jtunnel expose -p 5173`).

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

Uninstall also tries to remove the `JT Tunnel` firewall rule (may prompt for UAC).

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
jtunnel doctor                      # connectivity + Windows Firewall checks
jtunnel doctor -p 5173              # also verify local app port
jtunnel doctor --fix-firewall       # add firewall rule (UAC prompt, Windows only)
jtunnel logout
```

### Troubleshooting (`jtunnel doctor`)

```bash
jtunnel doctor
jtunnel doctor -p 5173
jtunnel doctor --fix-firewall
```

Checks:

- Signed-in state and allocated port block
- Reachability of `admin.new901.io:443` and `jtunnel.new901.io:443`
- Optional local app port (`-p`)
- On Windows: whether the `JT Tunnel` outbound firewall rule exists (loads `NetSecurity` explicitly; falls back to `netsh` if needed)

If the firewall rule is missing, run `jtunnel doctor --fix-firewall` (prompts for UAC once).

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

### Overrides

Host and API endpoints can be overridden per-device without reinstalling. Resolution
order for the tunnel host: `tunnel.json` → device token `tunnel_host` claim →
`JTUNNEL_HOST` env → built-in default.

| Env var | Purpose | Default |
|---------|---------|---------|
| `JTUNNEL_HOST` | Control-plane WebSocket URL (`ws://` or `wss://`) | `wss://jtunnel.new901.io` |
| `JTUNNEL_API_BASE` | Admin API base URL | `https://admin.new901.io` |

Example (Asia cutover without a reinstall):

```bash
export JTUNNEL_HOST=wss://sg.jtunnel.new901.io
jtunnel login   # or: re-issue device token with the new tunnel_host claim
```

Local files under the config dir:

| File | Purpose |
|------|---------|
| `device.jwt` | Device auth token |
| `tunnel.json` | Allocated port block + host |
| `tunnels.json` | Saved tunnel mappings (name → public/local ports) |
| `preferences.json` | Default service for quick Expose |

## Performance & limits

See [JT_TUNNEL.md](../JT_TUNNEL.md#performance--limits) for request timeout (5 min), WebSocket frame size (32MB), concurrency, and latency expectations.

Latency/throughput harness:

```bash
BASE_URL=https://jtunnel.new901.io:9001 scripts/bench.sh
```

Baseline numbers and client-side tuning (DNS resolver, TCP buffer sysctls) are
documented in [docs/PERF_BASELINE.md](docs/PERF_BASELINE.md). Caching relies on the
browser + Vite ETag revalidation (the tunnel ETag cache is off by default).

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
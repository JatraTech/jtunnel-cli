# JT Tunnel CLI

Local developer CLI for exposing services through JT Tunnel. Install the `jtunnel` command from this package.

## Quick start

```bash
# Interactive menu (recommended for daily use)
jtunnel

# Or step by step:
jtunnel login
npm run dev                 # e.g. localhost:5173
jtunnel expose -p 5173
```

Share the printed public URL (e.g. `https://jtunnel.new901.io:9001`).

See [JT_TUNNEL.md](../JT_TUNNEL.md) for full architecture and deployment docs.

## Commands

```bash
jtunnel                     # interactive menu
jtunnel login
jtunnel expose              # starts default saved tunnel, or prompts
jtunnel expose -p 5173
jtunnel expose api -p 8000
jtunnel expose --wizard     # multi-service (saved list or configure new)
jtunnel list
jtunnel status
jtunnel logout
```

Bare `jtunnel` menu:

| Item | Behavior |
|------|----------|
| **Expose** | Starts your **default** saved tunnel immediately (no confirm). If none, pick saved or configure new. |
| **Expose multiple** | Start all saved (up to 3), pick which saved to include, or configure new. |
| **List tunnels** | One-step: Start `name` / Set default / Back |
| Login / Logout / Quit | Auth and exit |

Port range and default service name appear in the header when signed in. Ctrl+C disconnects and returns to the menu (no extra Enter).

Scripted/CI usage keeps flags and never prompts when stdin is not a TTY.

## Configuration

Environment variables (see `jtunnel/config.py`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `JTUNNEL_API_BASE` | `http://localhost:8000` | Django API base URL |
| `JTUNNEL_HOST` | `wss://jtunnel.new901.io` | Go control WebSocket URL |
| `JTUNNEL_PUBLIC_HOST` | `jtunnel.new901.io` | Public tunnel hostname |
| `JTUNNEL_CONFIG_DIR` | `~/.config/jtunnel` | Local config directory |

After `jtunnel login`, port range and host can also come from `tunnel.json` or the device token.

Local port detection order for `jtunnel expose` (non-wizard):

1. `--port` / `-p` flag
2. `.jtunnel.toml` → `port` key
3. Default `3000`

Service names are labels only. Sticky public ports reuse the same name’s last mapping. Max 3 concurrent tunnels.

Last exposed service is remembered as the **default** in `preferences.json`.

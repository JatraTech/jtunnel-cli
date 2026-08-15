# JTunnel Performance Baseline

Baseline captured 2026-08-15 from the dev machine in Dhaka (BD) against the
US relay (`44.207.241.207`, AWS us-east-1). Re-run after each deployment with:

```bash
BASE_URL=https://jtunnel.new901.io:9001 scripts/bench.sh
```

## Network

| Path | TCP RTT | Notes |
|---|---|---|
| jtunnel relay (us-east-1) | 256 ms | dominant cost; immutable until the Asia cutover |
| VS Code tunnel relay (Singapore) | 47 ms | comparison target |
| Tailscale DERP (Bengaluru) | 69 ms | comparison target |
| Tailscale direct P2P | ~0–5 ms | unreachable for public browsers |

## Baseline (protocol v1: HTTP/1.1, full buffering, `Connection: close`)

| Metric | Value |
|---|---|
| `/` (1.4 KB) TTFB / total | 1.64 s / 1.64 s |
| `/@vite/client` (204 KB) total | 3.29 s (TTFB 2.13 s, transfer 1.16 s ≈ 176 KB/s) |
| `/src/main.tsx` (1.7 KB) | 1.15 s |
| TLS handshake (:9001) | ~0.62 s (~2.4 RTTs) |
| DNS lookup | ~0.19 s |
| First-load page (300+ assets, HTTP/1.1) | 30–60 s |

Local Vite alone (no tunnel): `/` = 2.7 ms, `/@vite/client` = 13 ms.

## Targets after protocol v2

| Metric | Target |
|---|---|
| `/` TTFB (US relay) | ~1.0 s (RTT floor: DNS + TCP + TLS + 2×tunnel RTT) |
| 204 KB asset | ~1.2 s / ~500 KB/s (larger TCP buffers + streaming) |
| First-load page (HTTP/2 + streaming) | ~10–15 s |
| Refresh/revalidation (ETag 304 cache) | near-0 per unchanged module |

## Ops notes for client machines

- **DNS**: point `systemd-resolved` at a fast upstream and enable positive
  caching (`/etc/systemd/resolved.conf` `DNS=1.1.1.1 8.8.8.8`,
  `Cache=yes`), then `systemctl restart systemd-resolved`.
- **TCP buffers** (bandwidth-delay product at 256 ms RTT):
  ```ini
  # /etc/sysctl.d/99-jtunnel.conf
  net.core.rmem_max = 2621440
  net.core.wmem_max = 2621440
  net.ipv4.tcp_window_scaling = 1
  ```
  Apply with `sysctl --system`. The CLI also sets 1 MiB SO_RCVBUF/SO_SNDBUF
  itself; the sysctls just allow it.
- Verify ALPN negotiates h2: `openssl s_client -connect jtunnel.new901.io:9001 -alpn h2,http/1.1` → `ALPN protocol: h2`.

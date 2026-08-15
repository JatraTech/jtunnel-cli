#!/usr/bin/env bash
# JTunnel latency/throughput benchmark harness.
#
# Usage:
#   BASE_URL=https://jtunnel.new901.io:9001 scripts/bench.sh
#
# Options (env):
#   BASE_URL   base URL to benchmark (default https://jtunnel.new901.io:9001)
#   PATHS      space-separated paths to time (default "/ /@vite/client /src/main.tsx")
#   REPEATS    repeats per path (default 3)
#   OUT        JSON output file (default /tmp/jtunnel-bench.json)
set -euo pipefail

BASE_URL="${BASE_URL:-https://jtunnel.new901.io:9001}"
PATHS="${PATHS:-/ /@vite/client /src/main.tsx}"
REPEATS="${REPEATS:-3}"
OUT="${OUT:-/tmp/jtunnel-bench.json}"

echo "Benchmarking ${BASE_URL}  (repeats=${REPEATS})"
echo

printf '["%s"' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$OUT"
first=1
for path in $PATHS; do
  for ((i = 1; i <= REPEATS; i++)); do
    json=$(curl -s -o /dev/null \
      -w '{"path":"%{url_effective}","dns":%{time_namelookup},"connect":%{time_connect},"tls":%{time_appconnect},"ttfb":%{time_starttransfer},"total":%{time_total},"bytes":%{size_download},"speed":%{speed_download}}' \
      --max-time 120 --http2 "${BASE_URL}${path}")
    if [ "$first" -eq 1 ]; then
      printf ',\n%s' "$json" >> "$OUT"
      first=0
    else
      printf ',\n%s' "$json" >> "$OUT"
    fi
  done
done
printf ']' >> "$OUT"

python3 - "$OUT" <<'PY'
import json
import statistics
import sys

results = json.load(open(sys.argv[1]))
rows = {}
for r in results[1:]:
    rows.setdefault(r["path"], []).append(r)

print(f'{"path":<38} {"ttfb(ms)":>10} {"total(ms)":>10} {"speed(KB/s)":>12}  samples')
print("-" * 80)
for path, samples in rows.items():
    ttfb = [s["ttfb"] * 1000 for s in samples]
    total = [s["total"] * 1000 for s in samples]
    speed = [s["speed"] / 1024 for s in samples]
    print(
        f'{path:<38} {statistics.median(ttfb):>10.0f} {statistics.median(total):>10.0f} '
        f'{statistics.median(speed):>12.1f}  {len(samples)}'
    )
PY
echo
echo "JSON written to ${OUT}"

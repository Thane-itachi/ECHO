# Stop the ECHO stack started by scripts/dev.sh
set -uo pipefail

for pattern in "[u]vicorn app.main:app" "[v]ite --host 127.0.0.1 --port 5173"; do
  pids="$(pgrep -f "$pattern" || true)"
  if [ -n "$pids" ]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null && echo "stopped: $pattern"
  fi
done

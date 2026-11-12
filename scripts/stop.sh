# Stop the ECHO stack started by scripts/dev.sh (pid files, not name matching:
# `pkill -f app.worker` also matches an editor or a grep that merely mentions it).
set -uo pipefail

for name in api worker web; do
  pidfile="/tmp/echo-$name.pid"
  [ -f "$pidfile" ] || continue
  pid="$(cat "$pidfile")"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null && echo "stopped: $name ($pid)"
  fi
  rm -f "$pidfile"
done
sleep 1

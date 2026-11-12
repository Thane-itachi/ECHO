# Start the whole ECHO stack locally: API on :8000, extraction worker, web app on :5173.
# Logs: /tmp/echo-api.log, /tmp/echo-worker.log, /tmp/echo-web.log    Stop: scripts/stop.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/backend"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  case "${ECHO_ENV:-development}" in
    production)
      echo "backend/.env is required in production (at minimum ECHO_DATA_KEY)." >&2
      exit 1
      ;;
    *)
      echo "warning: no backend/.env; content will be stored UNENCRYPTED (development only)." >&2
      echo "         copy backend/.env.example to backend/.env and set ECHO_DATA_KEY." >&2
      ;;
  esac
fi

start() { # start <name> <logfile> <command...>
  local name="$1" log="$2"
  shift 2
  local pidfile="/tmp/echo-$name.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "$name already running (pid $(cat "$pidfile"))"
    return 0
  fi
  nohup "$@" > "$log" 2>&1 &
  echo $! > "$pidfile"
  echo "$name started (pid $!)"
}

start api /tmp/echo-api.log python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning
start worker /tmp/echo-worker.log python3 -m app.worker

cd "$root/web"
if [ ! -d node_modules ]; then
  echo "installing web dependencies…"
  npm install --no-audit --no-fund
fi
start web /tmp/echo-web.log npm run dev -- --host 127.0.0.1 --port 5173

for _ in $(seq 1 40); do
  if curl -s -m 1 http://127.0.0.1:8000/healthz >/dev/null && curl -s -m 1 -o /dev/null http://127.0.0.1:5173/; then
    echo "ECHO is up: http://127.0.0.1:5173   (admin console: http://127.0.0.1:5173/admin)"
    exit 0
  fi
  sleep 1
done

echo "timed out waiting for ECHO; check /tmp/echo-api.log, /tmp/echo-worker.log and /tmp/echo-web.log" >&2
exit 1

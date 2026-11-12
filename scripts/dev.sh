# Start the whole ECHO stack locally: API on :8000, web app on :5173.
# Logs: /tmp/echo-api.log and /tmp/echo-web.log    Stop: scripts/stop.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$root/backend/.env" ]; then
  echo "backend/.env is missing. Copy backend/.env.example to backend/.env and fill ECHO_DATA_KEY." >&2
  exit 1
fi

cd "$root/backend"
if pgrep -f "[u]vicorn app.main:app" >/dev/null; then
  echo "api already running on :8000"
else
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning \
    > /tmp/echo-api.log 2>&1 &
  echo "api started (pid $!)"
fi

cd "$root/web"
if [ ! -d node_modules ]; then
  echo "installing web dependencies…"
  npm install --no-audit --no-fund
fi
if pgrep -f "[v]ite --host 127.0.0.1 --port 5173" >/dev/null; then
  echo "web app already running on :5173"
else
  nohup npm run dev -- --host 127.0.0.1 --port 5173 > /tmp/echo-web.log 2>&1 &
  echo "web app started (pid $!)"
fi

for _ in $(seq 1 30); do
  if curl -s -m 1 http://127.0.0.1:8000/healthz >/dev/null && curl -s -m 1 -o /dev/null http://127.0.0.1:5173/; then
    echo "ECHO is up: http://127.0.0.1:5173"
    exit 0
  fi
  sleep 1
done

echo "timed out waiting for ECHO; check /tmp/echo-api.log and /tmp/echo-web.log" >&2
exit 1

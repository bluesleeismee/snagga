#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ██████╗ ███████╗ █████╗ ██╗     ██████╗  █████╗ ██████╗  █████╗ ██████╗"
echo "  ██╔══██╗██╔════╝██╔══██╗██║     ██╔══██╗██╔══██╗██╔══██╗██╔══██╗██╔══██╗"
echo "  ██║  ██║█████╗  ███████║██║     ██████╔╝███████║██║  ██║███████║██████╔╝"
echo "  ██║  ██║██╔══╝  ██╔══██║██║     ██╔══██╗██╔══██║██║  ██║██╔══██║██╔══██╗"
echo "  ██████╔╝███████╗██║  ██║███████╗██║  ██║██║  ██║██████╔╝██║  ██║██║  ██║"
echo "  ╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝"
echo ""

# ── .env ────────────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "  ✓ .env aus .env.example erstellt"
fi

# ── Backend ─────────────────────────────────────────────────────────────────
echo "  → Starte Backend …"
cd "$ROOT/backend"

if [ ! -d ".venv" ]; then
  echo "  → Erstelle Python venv …"
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt -q

# .env in Backend laden
set -a; source "$ROOT/.env"; set +a

python -m uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --reload &
BACKEND_PID=$!
echo "  ✓ Backend läuft (PID $BACKEND_PID) → http://localhost:${PORT:-8000}"
echo "    API Docs: http://localhost:${PORT:-8000}/docs"

# ── Frontend ────────────────────────────────────────────────────────────────
echo "  → Starte Frontend …"
cd "$ROOT/frontend"

if [ ! -d "node_modules" ]; then
  echo "  → Installiere npm-Pakete …"
  npm install
fi

npm run dev &
FRONTEND_PID=$!
echo "  ✓ Frontend läuft (PID $FRONTEND_PID) → http://localhost:5173"
echo ""
echo "  Drücke Ctrl+C zum Beenden."

cleanup() {
  echo ""
  echo "  Stoppe DealRadar …"
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM
wait

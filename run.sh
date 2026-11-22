#!/usr/bin/env bash
# Sobe tudo do zero: dependências, banco, ingestão (snapshot real ou ao vivo), build da interface e servidor em :8000.
set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:-auto}"   # auto | live | snapshot

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r backend/requirements.txt
fi

NODE_BIN="$(command -v node || true)"
if [ -z "$NODE_BIN" ] && [ -d .tools/node-v22.11.0-darwin-arm64/bin ]; then export PATH="$PWD/.tools/node-v22.11.0-darwin-arm64/bin:$PATH"; fi
(cd frontend && [ -d node_modules ] || npm install --no-audit --no-fund) && (cd frontend && npm run build)

.venv/bin/python -m backend.worker init
.venv/bin/python -m backend.worker ingest all --mode "$MODE"
exec .venv/bin/python -m uvicorn backend.app.api:app --host 127.0.0.1 --port 8000

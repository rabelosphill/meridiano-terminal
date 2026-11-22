#!/bin/bash
# Gera media/meridiano-demo.mp4: grava o roteiro no Chrome headless e codifica com AVFoundation.
# O estado de tela da usuária "ana" é salvo antes e restaurado depois (a gravação não altera o seu workspace).
# Requer o servidor rodando em 127.0.0.1:8000 e o Google Chrome instalado.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${1:-$(mktemp -d)}"
cd "$ROOT"
export PATH="$ROOT/.tools/node-v22.11.0-darwin-arm64/bin:$PATH"
mkdir -p "$WORK" media
.venv/bin/python -m scripts.demo.workspace backup "$WORK/ana-workspace.json"
trap '.venv/bin/python -m scripts.demo.workspace restore "$WORK/ana-workspace.json"; pkill -f "remote-debugging-port=9333" || true' EXIT
.venv/bin/python -m scripts.demo.workspace clear "$WORK/ana-workspace.json"
node scripts/demo/record.mjs "$WORK"
swift scripts/demo/encode.swift "$WORK" "$ROOT/media/meridiano-demo.mp4"

#!/bin/bash
# Atualização agendada do Meridiano (chamada pelo launchd). Uso: scripts/update.sh news|daily|weekly
# - news   : comunicados SEC 8-K/6-K, Fed e Copom (a cada 30 min)
# - daily  : pregões B3 dos últimos 7 dias, preços EUA (Tiingo), fundamentos SEC, séries BCB/FRED (2x ao dia)
# - weekly : DFP/ITR e fatos relevantes da CVM (domingo)
# Trava por rotina (não roda duas vezes ao mesmo tempo), log em logs/update.log, segredos lidos do .env.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOB="${1:-daily}"
LOG="$ROOT/logs/update.log"
LOCK="$ROOT/logs/.lock-$JOB"
mkdir -p "$ROOT/logs"
case "$JOB" in news) TARGET=news_fast ;; daily) TARGET=daily ;; weekly) TARGET=weekly ;; *) echo "rotina desconhecida: $JOB" >&2; exit 2 ;; esac

if ! mkdir "$LOCK" 2>/dev/null; then
  # trava antiga (> 2 h) é de uma execução que morreu: remove e segue
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then rmdir "$LOCK"; mkdir "$LOCK"; else
    echo "$(date '+%F %T') [$JOB] já em execução — pulando" >> "$LOG"; exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# log simples com rotação (mantém ~5 MB)
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG")" -gt 5000000 ]; then mv "$LOG" "$LOG.1"; fi

cd "$ROOT"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
START=$(date +%s)
echo "$(date '+%F %T') [$JOB] início" >> "$LOG"
OUT=$("$ROOT/.venv/bin/python" -m backend.worker ingest "$TARGET" --mode live 2>&1)
RC=$?
# resumo: só contagens (nunca imprime segredos)
SUMMARY=$(printf '%s' "$OUT" | "$ROOT/.venv/bin/python" "$ROOT/scripts/summarize.py")
[ -n "${TIINGO_API_KEY:-}" ] && SUMMARY=${SUMMARY//$TIINGO_API_KEY/***}
echo "$(date '+%F %T') [$JOB] fim rc=$RC em $(( $(date +%s) - START ))s · $SUMMARY" >> "$LOG"
exit $RC

"""Resumo de uma ingestão para o log: só contagens por conector (nunca imprime segredos)."""
import json
import sys

t = sys.stdin.read()
try:
    d = json.loads(t)
    print(" ".join(f"{k}={v.get('inserted', 0)}" for k, v in d.items() if isinstance(v, dict)))
except Exception:
    lines = t.strip().splitlines()
    print("ERRO: " + lines[-1][:300] if lines else "sem saída")

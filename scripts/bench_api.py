"""Benchmark reprodutível da API (critério H, lado servidor). Requer o servidor rodando em :8000.

  .venv/bin/python scripts/bench_api.py
"""
import platform
import statistics
import subprocess
import time

import httpx

BASE = "http://127.0.0.1:8000"


def pct(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s) * p))]


def main():
    c = httpx.Client(base_url=BASE, headers={"X-User": "ana"}, timeout=30)
    issuers = {}
    for t in ("PETR4 B3 OVERVIEW", "AAPL NASDAQ OVERVIEW", "VALE3 B3 OVERVIEW"):
        p = c.post("/api/command/parse", json={"text": t}).json()
        issuers[t.split()[0]] = p["issuer_id"]
    screens = [(i, st, fq) for i in issuers.values() for st in ("IS", "BS", "CF") for fq in ("A", "Q", "LTM")]
    # 1ª abertura (cache do servidor frio para cada combinação)
    cold = []
    for i, st, fq in screens:
        t0 = time.perf_counter()
        c.get(f"/api/issuers/{i}/statements", params={"statement": st, "freq": fq, "as_of": "2099-01-01"})
        cold.append((time.perf_counter() - t0) * 1000)
    # cache quente
    warm = []
    for _ in range(10):
        for i, st, fq in screens:
            t0 = time.perf_counter()
            c.get(f"/api/issuers/{i}/statements", params={"statement": st, "freq": fq, "as_of": "2099-01-01"})
            warm.append((time.perf_counter() - t0) * 1000)
    parse = []
    for _ in range(200):
        t0 = time.perf_counter()
        c.post("/api/command/parse", json={"text": "PETR4 B3 FIN Q"})
        parse.append((time.perf_counter() - t0) * 1000)
    facts = c.get("/api/health").json()
    cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip() if platform.system() == "Darwin" else platform.processor()
    print(f"máquina: {cpu} · {platform.system()} {platform.release()} · Python {platform.python_version()} · {facts['db']}")
    print(f"telas: {len(screens)} combinações (3 emissores × IS/BS/CF × A/Q/LTM)")
    for name, xs in (("statements frio", cold), ("statements cache", warm), ("parse de comando", parse)):
        print(f"{name:18} n={len(xs):4} p50={statistics.median(xs):7.1f} ms  p95={pct(xs, .95):7.1f} ms  max={max(xs):7.1f} ms")


if __name__ == "__main__":
    main()

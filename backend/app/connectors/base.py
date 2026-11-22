"""Infraestrutura comum dos conectores: limites por fonte, retentativa com espera progressiva,
paginação, payload bruto em storage, idempotência, quarentena e replay."""
import json
import random
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Iterator, Optional

import httpx

from .. import config
from ..db import tx
from ..storage import store


class SourceUnavailable(Exception):
    pass


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second if per_second else 0
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
            self._next = max(now, self._next) + self.interval


class HttpClient:
    """GET com limite por fonte e backoff exponencial com jitter (429/5xx/erros de rede)."""

    def __init__(self, source: str, per_second: float, headers: Optional[dict] = None,
                 max_retries: int = 4, base_delay: float = 0.5, transport=None):
        self.source = source
        self.limiter = RateLimiter(per_second)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.client = httpx.Client(headers=headers or {}, timeout=60, follow_redirects=True, transport=transport)
        self.attempts = 0

    def get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        last: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            self.attempts += 1
            wait = self.base_delay * (2 ** attempt) + random.uniform(0, 0.1)
            try:
                r = self.client.get(url, params=params)
            except httpx.TransportError as e:
                last = e
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    last = Exception(f"HTTP {r.status_code}")
                    wait = max(wait, float(r.headers.get("Retry-After", 0) or 0))
                else:
                    r.raise_for_status()   # 4xx não é retentável
                    return r
            if attempt < self.max_retries:
                time.sleep(wait)
        raise SourceUnavailable(f"{self.source}: {url} indisponível após {self.max_retries + 1} tentativas ({last})")

    def paginate(self, url: str, page_param: str, start: int, size_param: str, size: int,
                 extract: Callable[[httpx.Response], list]) -> Iterator[list]:
        page = start
        while True:
            items = extract(self.get(url, params={page_param: page, size_param: size}))
            if not items:
                return
            yield items
            if len(items) < size:
                return
            page += 1


def save_raw(conn, source: str, request: str, data: bytes, mode: str, fetched_at: Optional[str] = None) -> int:
    key, sha = store.put(data)
    row = conn.execute("""INSERT INTO raw_payload(source,request,object_key,sha256,bytes,fetched_at,mode)
                          VALUES (%s,%s,%s,%s,%s,%s,%s)
                          ON CONFLICT (source,sha256) DO UPDATE SET request=raw_payload.request
                          RETURNING id""",
                       (source, request, key, sha, len(data), fetched_at or datetime.now(timezone.utc).isoformat(), mode)).fetchone()
    return row["id"]


class Run:
    """Contexto de uma execução de ingestão (estatísticas + quarentena)."""

    def __init__(self, connector: str, mode: str):
        self.connector, self.mode = connector, mode
        self.stats = {"inserted": 0, "skipped_existing": 0, "quarantined": 0, "revisions": 0}
        with tx() as c:
            self.id = c.execute("INSERT INTO ingestion_run(connector,mode) VALUES (%s,%s) RETURNING id", (connector, mode)).fetchone()["id"]

    def quarantine(self, conn, record: dict, reason: str):
        self.stats["quarantined"] += 1
        conn.execute("INSERT INTO quarantine(run_id,connector,record,reason) VALUES (%s,%s,%s,%s)",
                     (self.id, self.connector, json.dumps(record, default=str), reason))

    def finish(self, status: str = "ok", error: Optional[str] = None):
        with tx() as c:
            c.execute("UPDATE ingestion_run SET finished_at=now(), status=%s, stats=%s, error=%s WHERE id=%s",
                      (status, json.dumps(self.stats), error, self.id))
        return self.stats


def snapshot_manifest() -> dict:
    p = config.SNAPSHOT_DIR / "manifest.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    return {f["path"]: f for f in m["files"]}


def resolve_mode(requested: Optional[str]) -> str:
    return requested or config.DATA_MODE

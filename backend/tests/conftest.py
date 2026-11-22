"""Ambiente de teste isolado: banco e storage próprios (FT_ENV=test), ingestão do snapshot real, feed simulado desligado."""
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("FT_ENV", "test")
os.environ.setdefault("FT_PGDATA", str(ROOT / ".pgdata_test"))
os.environ.setdefault("FT_OBJECT_STORE", tempfile.mkdtemp(prefix="meridiano-objects-"))
os.environ["FT_SIM_FEED"] = "0"
os.environ["FT_DATA_MODE"] = "snapshot"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def loaded_db():
    from backend.app import db
    from backend import worker
    db.reset_schema()
    worker.init()
    stats = worker.ingest("all", "snapshot")
    return stats


@pytest.fixture(scope="session")
def client(loaded_db):
    from fastapi.testclient import TestClient
    from backend.app.api import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def ids(loaded_db):
    from backend.app import db
    r = {x["short_name"]: str(x["id"]) for x in db.q("SELECT id, short_name FROM issuer")}
    r.update({f"L:{x['ticker']}": str(x["id"]) for x in db.q("SELECT id, ticker FROM listing")})
    return r

"""Configuração via variáveis de ambiente (ver .env.example). Nenhum segredo no código."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


ENV = _env("FT_ENV", "dev")                       # dev | test | prod
DATABASE_URL = os.environ.get("DATABASE_URL")     # se ausente em dev/test: PostgreSQL embutido (pgserver)
PGDATA_DIR = Path(_env("FT_PGDATA", str(ROOT / ".pgdata")))
OBJECT_STORE_DIR = Path(_env("FT_OBJECT_STORE", str(ROOT / "data" / "objects")))
SNAPSHOT_DIR = Path(_env("FT_SNAPSHOT_DIR", str(ROOT / "data" / "snapshot")))
SEC_USER_AGENT = _env("SEC_USER_AGENT", "FinTerminal-dev research-bot@example.com")
DATA_MODE = _env("FT_DATA_MODE", "auto")          # live | snapshot | auto (tenta live, cai para snapshot)
SIM_FEED = _env("FT_SIM_FEED", "1" if ENV != "prod" else "0") == "1"
SIM_IGNORE_HOURS = _env("FT_SIM_IGNORE_HOURS", "1") == "1"
QUOTE_STALE_SECONDS = int(_env("FT_QUOTE_STALE_SECONDS", "30"))

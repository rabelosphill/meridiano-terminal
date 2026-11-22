"""Armazenamento de objetos endereçado por conteúdo.

Interface mínima compatível com S3 (put/get/exists por chave). A implementação local
grava em data/objects/<sha256[:2]>/<sha256>; trocar por S3/MinIO = nova classe com a mesma API.
"""
import hashlib
from pathlib import Path
from typing import Tuple

from . import config


class LocalObjectStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> Tuple[str, str]:
        sha = hashlib.sha256(data).hexdigest()
        key = f"{sha[:2]}/{sha}"
        p = self.root / key
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(p)
        return key, sha

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()


store = LocalObjectStore(config.OBJECT_STORE_DIR)

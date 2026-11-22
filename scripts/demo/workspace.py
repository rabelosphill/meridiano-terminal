"""Salva/restaura o estado de tela de um usuário para que a gravação do vídeo não altere o seu workspace.
Uso: python scripts/demo/workspace.py backup|clear|restore <arquivo.json> [usuario]"""
import json
import sys

from backend.app.db import q, tx

cmd, path = sys.argv[1], sys.argv[2]
user = sys.argv[3] if len(sys.argv) > 3 else "ana"
if cmd == "backup":
    rows = q("SELECT workspace, scope_key, state, updated_at FROM workspace_state WHERE user_id=%s", (user,))
    json.dump(rows, open(path, "w"), default=str)
    print(f"backup: {len(rows)} estados")
elif cmd == "clear":
    with tx() as c:
        c.execute("DELETE FROM workspace_state WHERE user_id=%s", (user,))
elif cmd == "restore":
    rows = json.load(open(path))
    with tx() as c:
        c.execute("DELETE FROM workspace_state WHERE user_id=%s", (user,))
        for r in rows:
            c.execute("INSERT INTO workspace_state(user_id,workspace,scope_key,state,updated_at) VALUES (%s,%s,%s,%s,%s)",
                      (user, r["workspace"], r["scope_key"], json.dumps(r["state"]), r["updated_at"]))
    print(f"restaurado: {len(rows)} estados")

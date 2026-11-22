"""Permissões por usuário × feed × campo × ação (view/export). Regra mais específica vence; padrão = negar."""
import json
from typing import Optional

from fastapi import Header, HTTPException

from ..db import q, q1, tx


def entitlement(user: str, feed: str, field: str) -> Optional[dict]:
    rows = q("SELECT * FROM entitlement WHERE user_id=%s AND feed IN (%s,'*') AND field IN (%s,'*')", (user, feed, field))
    if not rows:
        return None
    rows.sort(key=lambda r: ((r["feed"] != "*") * 2 + (r["field"] != "*")), reverse=True)
    return rows[0]


def allowed(user: str, feed: str, field: str, action: str) -> bool:
    e = entitlement(user, feed, field)
    return bool(e and (e["can_export"] if action == "export" else e["can_view"]))


def audit(user: str, action: str, detail: dict, ok: bool):
    with tx() as c:
        c.execute("INSERT INTO audit_log(user_id,action,detail,allowed) VALUES (%s,%s,%s,%s)", (user, action, json.dumps(detail, default=str), ok))


def require(user: str, feed: str, field: str, action: str, detail: Optional[dict] = None):
    ok = allowed(user, feed, field, action)
    audit(user, f"{action}:{feed}:{field}", detail or {}, ok)
    if not ok:
        raise HTTPException(403, detail={"error": "forbidden", "message": f"Usuário '{user}' sem permissão de {action} para {field} ({feed}).",
                                         "feed": feed, "field": field, "action": action})


def current_user(x_user: Optional[str] = Header(None)) -> str:
    """Autenticação de desenvolvimento: cabeçalho X-User. Em produção, substituir por OIDC/SSO (mesma interface)."""
    u = x_user or "ana"
    if not q1("SELECT 1 FROM app_user WHERE id=%s", (u,)):
        raise HTTPException(401, detail={"error": "unknown_user", "message": f"usuário '{u}' desconhecido"})
    return u

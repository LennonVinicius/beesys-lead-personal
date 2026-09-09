import os
import time
from typing import Optional

import requests
from fastapi import Depends, Header, HTTPException

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
AUTH_REQUIRED = (os.getenv("AUTH_REQUIRED", "true").lower() not in {"0", "false", "no"})
_CACHE = {}


def _validate_token(token: str):
    now = time.monotonic()
    cached = _CACHE.get(token)
    if cached and cached[0] > now:
        return cached[1]
    if not SUPABASE_URL or not SUPABASE_KEY:
        if AUTH_REQUIRED:
            raise HTTPException(503, "Supabase Auth não configurado no backend")
        return {"email": "dev@local", "id": "dev"}
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"},
            timeout=8,
        )
    except requests.RequestException:
        raise HTTPException(503, "Não foi possível validar a sessão")
    if r.status_code != 200:
        raise HTTPException(401, "Sessão inválida ou expirada")
    user = r.json()
    _CACHE[token] = (now + 30, user)
    if len(_CACHE) > 256:
        for key in list(_CACHE)[:64]:
            _CACHE.pop(key, None)
    return user


def get_current_user(authorization: Optional[str] = Header(default=None)):
    if not AUTH_REQUIRED and not authorization:
        return {"email": "dev@local", "id": "dev"}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Autenticação necessária")
    return _validate_token(authorization.split(" ", 1)[1].strip())


def current_email(user=Depends(get_current_user)) -> str:
    return (user.get("email") or user.get("user_metadata", {}).get("email") or "").lower()

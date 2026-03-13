"""
auth.py -- Optional token authentication.

When UI_AUTH_TOKEN is set, requests must include the token via:
  - Query param:  ?token=<token>
  - Cookie:       claude_auth=<token>
  - Header:       Authorization: Bearer <token>
"""

from typing import Optional
from . import config


def _token_valid(token: Optional[str]) -> bool:
    if not config.UI_AUTH_TOKEN:
        return True
    return token is not None and token.strip() == config.UI_AUTH_TOKEN.strip()


def check_api_auth(request=None):
    if not config.UI_AUTH_TOKEN:
        return
    # Import FastAPI inside function to allow test-time stubbing
    try:
        from fastapi import HTTPException
    except ImportError:
        class HTTPException(Exception):
            def __init__(self, status_code=400, detail=""): pass

    if request is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    auth_header = getattr(getattr(request, 'headers', None), 'get', lambda k, d=None: d)("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None
    if not token:
        params = getattr(request, 'query_params', {})
        token = params.get("token") if hasattr(params, 'get') else None
    if not _token_valid(token):
        raise HTTPException(status_code=401, detail="Unauthorized.")


def check_ui_auth(request=None, claude_auth=None):
    if not config.UI_AUTH_TOKEN:
        return None
    token = None
    if request is not None:
        params = getattr(request, 'query_params', {})
        token = params.get("token") if hasattr(params, 'get') else None
    if not token:
        token = claude_auth
    if not token and request is not None:
        auth_header = getattr(getattr(request, 'headers', None), 'get', lambda k, d=None: d)("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()

    if not _token_valid(token):
        try:
            from fastapi import HTTPException
        except ImportError:
            class HTTPException(Exception):
                def __init__(self, status_code=400, detail=""): pass
        raise HTTPException(status_code=401, detail="Auth required. Add ?token=<your-token>")
    return token

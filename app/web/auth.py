"""后台登录：单用户 + 签名 cookie。

后台默认只绑 127.0.0.1，通过 SSH 隧道访问，所以不做用户体系、不做 CSRF token
（同源 + 无公网入口）。真要对外暴露，请自己套反代 + HTTPS，并把这里换成
更严肃的方案。
"""
from __future__ import annotations

import hmac
import logging
import secrets
import time

from fastapi import Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, TimestampSigner

from config.settings import settings

log = logging.getLogger(__name__)

COOKIE = "tcw_session"
MAX_AGE = 7 * 24 * 3600

_signer: TimestampSigner | None = None


def _get_signer() -> TimestampSigner:
    global _signer
    if _signer is None:
        secret = settings.web_secret.strip()
        if not secret:
            # 没配就临时生成：重启后所有人都要重新登录，但不至于用固定弱密钥
            secret = secrets.token_urlsafe(48)
            log.warning("WEB_SECRET 没配置，本次运行用临时密钥，重启后需重新登录")
        _signer = TimestampSigner(secret)
    return _signer


def password_ok(candidate: str) -> bool:
    expected = settings.web_password
    if not expected:
        return False
    # 定长比较，避免时序侧信道
    return hmac.compare_digest(candidate.encode(), expected.encode())


def issue(response) -> None:
    token = _get_signer().sign(str(int(time.time()))).decode()
    response.set_cookie(
        COOKIE, token,
        max_age=MAX_AGE,
        httponly=True,
        samesite="lax",
        # 绑 127.0.0.1 走 http，置 secure 会让 cookie 根本发不出去
        secure=False,
    )


def clear(response) -> None:
    response.delete_cookie(COOKIE)


def is_authed(request: Request) -> bool:
    token = request.cookies.get(COOKIE)
    if not token:
        return False
    try:
        _get_signer().unsign(token, max_age=MAX_AGE)
        return True
    except BadSignature:
        return False


PUBLIC_PATHS = {"/login", "/static", "/healthz"}


async def middleware(request: Request, call_next):
    path = request.url.path
    if any(path == p or path.startswith(p + "/") for p in PUBLIC_PATHS):
        return await call_next(request)
    if not is_authed(request):
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)

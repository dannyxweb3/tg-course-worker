"""管理后台：FastAPI + Jinja2 服务端渲染。

不上 React：这台机器没有 Node，"少维护"的核心就是不引入构建步骤。
后台和 bot 跑在同一个进程里，直接复用 db 层和 pipeline，不需要另造一套 API。
"""
from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.web import auth
from config.settings import settings

log = logging.getLogger(__name__)

WEB_ROOT = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    app = FastAPI(title="tg-course-worker 后台", docs_url=None, redoc_url=None)
    app.add_middleware(BaseHTTPMiddleware, dispatch=auth.middleware)
    app.mount(
        "/static", StaticFiles(directory=WEB_ROOT / "static"), name="static"
    )

    from app.web import routes, routes_admin, routes_ingest

    app.include_router(routes.router)
    app.include_router(routes_ingest.router)
    app.include_router(routes_admin.router)
    return app


async def serve() -> None:
    """作为 asyncio task 跑，和两个 bot 的 polling 并列。"""
    if not settings.web_enabled:
        log.info("后台未启用（WEB_ENABLED=false）")
        return
    if not settings.web_password.strip():
        log.warning("WEB_PASSWORD 没配置，后台不启动——不给无密码的入口留口子")
        return

    config = uvicorn.Config(
        create_app(),
        host=settings.web_host,
        port=settings.web_port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    log.info(
        "后台已启动：http://%s:%s（默认只绑本机，用 SSH 隧道访问）",
        settings.web_host, settings.web_port,
    )
    await server.serve()

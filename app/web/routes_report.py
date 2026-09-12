"""竞品分析：report/ 目录的只读展示。

没有任何写操作——数据是 git 里的静态文件，改分析走提交，不走后台。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import report
from app.web.deps import page

router = APIRouter()


@router.get("/reports", response_class=HTMLResponse)
async def report_list(request: Request):
    return page(request, "reports.html", idx=report.index())


@router.get("/reports/{slug}", response_class=HTMLResponse)
async def report_detail(request: Request, slug: str):
    found = report.detail(slug)
    if found is None:
        return page(
            request, "report_detail.html",
            data=None, body="", err=f"没有 {slug} 这份报告",
        )
    data, body = found
    return page(request, "report_detail.html", data=data, body=body)

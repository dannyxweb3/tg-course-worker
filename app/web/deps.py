"""模板环境和几个共用的小工具。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models import AssetKind, ItemStatus, Level
from config.settings import settings

WEB_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=WEB_ROOT / "templates")


def _fmt_dt(value: str | None, fmt: str = "%m-%d %H:%M") -> str:
    """库里存的是 UTC ISO，展示时转成本地时区。"""
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    if dt.tzinfo is not None:
        dt = dt.astimezone(settings.tz)
    return dt.strftime(fmt)


def _ago(value: str | None) -> str:
    if not value:
        return "从未"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    if dt.tzinfo is None:
        return value
    delta = datetime.now(settings.tz) - dt.astimezone(settings.tz)
    secs = int(delta.total_seconds())
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{secs // 60} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    return f"{secs // 86400} 天前"



def _num(value) -> str:
    """12345 → 12,345。报告里的订阅数、阅读量都不小，不分节读不出量级。"""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _cny(value) -> str:
    """报告里的钱一律是 [下限, 上限] 两元数组，上下限相等时不重复写。"""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return "—"
    lo, hi = value
    try:
        lo, hi = int(lo), int(hi)
    except (TypeError, ValueError):
        return "—"
    return f"¥{lo:,}" if lo == hi else f"¥{lo:,}–{hi:,}"

def _dash(value):
    """None 统一显示成破折号。报告里不是每个频道都测得到每个指标
    （比如 t.me/s 预览页看不到转发数），别把 Python 的 None 漏到页面上。"""
    return "—" if value is None or value == "" else value


def _pct(value) -> str:
    return "—" if value is None else f"{value}%"


STATUS_LABEL = {
    "new": "待分类",
    "classified": "已分类",
    "review": "待审核",
    "approved": "待发布",
    "published": "已发布",
    "discarded": "已丢弃",
    "failed": "出错",
}

# 素材库筛选下拉的选项。值可以是逗号分隔的多状态——"处理中" 就是把
# 待分类和已分类合成一格，和总览页那块统计对齐。
STATUS_FILTERS = [
    ("", "全部状态"),
    ("new,classified", "处理中"),
    ("review", "待审核"),
    ("approved", "待发布"),
    ("published", "已发布"),
    ("discarded", "已丢弃"),
    ("failed", "出错"),
]

templates.env.filters["dt"] = _fmt_dt
templates.env.filters["ago"] = _ago
templates.env.filters["num"] = _num
templates.env.filters["cny"] = _cny
templates.env.filters["dash"] = _dash
templates.env.filters["pct"] = _pct
templates.env.globals["STATUS_LABEL"] = STATUS_LABEL
templates.env.globals["ALL_STATUS"] = [str(s) for s in ItemStatus]
templates.env.globals["STATUS_FILTERS"] = STATUS_FILTERS
templates.env.globals["ALL_LEVELS"] = [(str(l), l.label) for l in Level]
# 仓库文件（vault）要等资料仓库频道接进来才能用，先不放进表单
templates.env.globals["ASSET_KINDS"] = [
    (str(k), k.label, k.icon)
    for k in (AssetKind.LINK, AssetKind.SOURCE, AssetKind.FULLTEXT)
]
templates.env.globals["ASSET_ICON"] = {str(k): k.icon for k in AssetKind}
templates.env.globals["ASSET_LABEL"] = {str(k): k.label for k in AssetKind}


templates.env.globals["RISK_LABEL"] = {
    "low": "低风险", "medium": "中风险", "high": "高风险", "criminal": "刑事",
}
templates.env.globals["CONF_LABEL"] = {
    "high": "证据充分", "medium": "抽样推断", "low": "推测",
}
templates.env.globals["PAID_LABEL"] = {
    "none": "无", "subs": "买粉", "engagement": "刷互动",
    "exchange": "互推换量", "mixed": "混合", "unknown": "未知",
}


def redirect(path: str, msg: str = "", err: str = "") -> RedirectResponse:
    """POST-Redirect-GET，顺带把提示信息带回页面。

    path 本身可能已经带查询串（如 /items/3?draft=7），所以分隔符要看情况选，
    不能一律用 "?"。
    """
    params = {k: v for k, v in (("msg", msg), ("err", err)) if v}
    if params:
        sep = "&" if "?" in path else "?"
        path = f"{path}{sep}{urlencode(params)}"
    return RedirectResponse(path, status_code=303)


def page(request, name: str, **ctx):
    ctx.setdefault("msg", request.query_params.get("msg", ""))
    ctx.setdefault("err", request.query_params.get("err", ""))
    return templates.TemplateResponse(request, name, ctx)

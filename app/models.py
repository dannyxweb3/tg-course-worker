"""领域模型与状态枚举。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceType(StrEnum):
    TEXT = "text"          # 直接发的文字
    URL = "url"            # 消息里含链接，抓正文
    DOCUMENT = "document"  # .md / .txt / .pdf
    FORWARD = "forward"    # 从其他群/频道转发来的消息


class Level(StrEnum):
    """处理档位。默认值由 classify 给出，审核时可随时切换重跑。"""

    P0 = "P0"  # 原样，只清噪音
    P1 = "P1"  # 轻排版
    P2 = "P2"  # 重写
    P3 = "P3"  # 丢弃

    @property
    def label(self) -> str:
        return {
            "P0": "原样清理",
            "P1": "轻排版",
            "P2": "重写",
            "P3": "丢弃",
        }[self.value]

    @classmethod
    def coerce(cls, value: str, default: "Level") -> "Level":
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            return default


class AssetKind(StrEnum):
    """配套资料的类型。

    link / source / fulltext 都是 URL，直接发链接；
    vault 存的是「资料仓库频道」里的消息 id，发货时用 copyMessage 转给用户
    ——file_id 是绑定 bot 的，生产 bot 拿到的 file_id 售卖 bot 用不了，
    所以文件类资料必须走仓库频道中转。
    """

    LINK = "link"          # 网盘 / GitHub / 任意外链
    SOURCE = "source"      # 原文出处
    FULLTEXT = "fulltext"  # 全文页（Telegraph）
    VAULT = "vault"        # 资料仓库频道里的一条消息

    @property
    def label(self) -> str:
        return {
            "link": "外链 / 网盘",
            "source": "原文出处",
            "fulltext": "全文页",
            "vault": "仓库文件",
        }[self.value]

    @property
    def icon(self) -> str:
        return {"link": "🔗", "source": "📄", "fulltext": "📰", "vault": "📎"}[
            self.value
        ]


class BotRole(StrEnum):
    PRODUCER = "producer"    # 收素材、审核（私聊，仅 OWNER）
    PUBLISHER = "publisher"  # 频道发布身份，必须是频道管理员
    SALE = "sale"            # 面向读者，接深链和发货

    @property
    def label(self) -> str:
        return {"producer": "生产", "publisher": "发布", "sale": "售卖"}[self.value]


class ItemStatus(StrEnum):
    NEW = "new"                # 刚入库，待分类
    CLASSIFIED = "classified"  # 已分类，待生成
    REVIEW = "review"          # 有草稿，待审核
    APPROVED = "approved"      # 通过，已进队列
    PUBLISHED = "published"    # 已发布
    DISCARDED = "discarded"    # 丢弃
    FAILED = "failed"          # 流水线出错


@dataclass(slots=True)
class Draft:
    """一版文案。同一素材可以有多版，随时回退。"""

    title: str
    tldr: str
    body_html: str
    tags: list[str] = field(default_factory=list)
    attribution: str = ""
    note: str = ""
    level: Level = Level.P1
    version: int = 1
    id: int | None = None
    item_id: int | None = None
    channel_id: int = 0       # 面向哪个频道写的，0 = 通用
    revise_note: str = ""
    edited_by: str = "llm"    # llm | human

    @property
    def char_count(self) -> int:
        return len(self.body_html)

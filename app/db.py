"""SQLite 存储层。规模小、单机、写入量低，不上 Postgres。

两条贯穿全局的设计原则：

1. **素材原文永久保留**。prompt 迭代之后要能重跑历史素材。
2. **bot token 不入库**，只存环境变量名。数据库要备份、要挂卷、后台页面可能
   误显示，明文 token 泄露等于 bot 被接管。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.models import Draft, ItemStatus, Level
from config.settings import settings

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
-- 批处理脚本和常驻服务会同时连这个库。没有 busy_timeout 的话，
-- 拿不到写锁就是无限干等（表现为脚本卡死），有它就会重试 10 秒再报错。
PRAGMA busy_timeout=10000;

-- ---------- 配置层：bot / 方向 / 频道 ----------

CREATE TABLE IF NOT EXISTS bots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL UNIQUE,
    role           TEXT NOT NULL,              -- producer | publisher | sale
    token_env_key  TEXT NOT NULL,              -- 环境变量名，不是 token 本身
    username       TEXT DEFAULT '',
    is_active      INTEGER DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verticals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    slug                TEXT NOT NULL UNIQUE,
    description         TEXT DEFAULT '',       -- 喂给分类器，决定素材归谁
    style_prompt        TEXT DEFAULT '',       -- 空则回落到 system_style.md
    relevance_threshold INTEGER DEFAULT 5,
    is_active           INTEGER DEFAULT 1,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    chat_id           INTEGER NOT NULL UNIQUE,
    username          TEXT DEFAULT '',
    publisher_bot_id  INTEGER REFERENCES bots(id),
    sale_bot_id       INTEGER REFERENCES bots(id),
    linked_group_id   INTEGER DEFAULT 0,
    vertical_id       INTEGER REFERENCES verticals(id),
    publish_cron      TEXT DEFAULT '0 9 * * *',
    timezone          TEXT DEFAULT 'Asia/Shanghai',
    is_active         INTEGER DEFAULT 1,
    health_status     TEXT DEFAULT 'unknown',  -- ok | error | unknown
    health_detail     TEXT DEFAULT '',
    health_checked_at TEXT DEFAULT '',
    created_at        TEXT NOT NULL
);

-- ---------- 内容层 ----------

CREATE TABLE IF NOT EXISTS items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id       INTEGER DEFAULT 0,       -- 分类器路由的结果，可人工改
    source_type       TEXT NOT NULL,
    source_url        TEXT DEFAULT '',
    source_title      TEXT DEFAULT '',
    source_link       TEXT DEFAULT '',
    raw_text          TEXT NOT NULL,
    media_json        TEXT DEFAULT '[]',
    dedup_key         TEXT DEFAULT '',
    status            TEXT NOT NULL,
    relevance         INTEGER DEFAULT -1,
    topic_tags        TEXT DEFAULT '[]',
    suggested_level   TEXT DEFAULT '',
    classify_reason   TEXT DEFAULT '',
    route_scores      TEXT DEFAULT '{}',       -- {vertical_slug: 分数}
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_vertical ON items(vertical_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_dedup
    ON items(dedup_key) WHERE dedup_key <> '';

CREATE TABLE IF NOT EXISTS drafts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      INTEGER NOT NULL REFERENCES items(id),
    channel_id   INTEGER DEFAULT 0,            -- 面向哪个频道写的，0=通用
    version      INTEGER NOT NULL,
    level        TEXT NOT NULL,
    title        TEXT NOT NULL,
    tldr         TEXT DEFAULT '',
    body_html    TEXT NOT NULL,
    tags         TEXT DEFAULT '[]',
    attribution  TEXT DEFAULT '',
    note         TEXT DEFAULT '',
    revise_note  TEXT DEFAULT '',
    edited_by    TEXT DEFAULT '',              -- llm | human
    created_at   TEXT NOT NULL,
    UNIQUE(item_id, version)
);
CREATE INDEX IF NOT EXISTS idx_drafts_item ON drafts(item_id);

-- 一稿多投：同一素材可以进多个频道的队列，各自一个版本
CREATE TABLE IF NOT EXISTS queue (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      INTEGER NOT NULL REFERENCES items(id),
    channel_id   INTEGER NOT NULL REFERENCES channels(id),
    draft_id     INTEGER NOT NULL REFERENCES drafts(id),
    priority     INTEGER DEFAULT 0,
    pin_date     TEXT DEFAULT '',
    created_at   TEXT NOT NULL,
    UNIQUE(item_id, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_queue_channel ON queue(channel_id);

CREATE TABLE IF NOT EXISTS published (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL REFERENCES items(id),
    channel_id      INTEGER NOT NULL REFERENCES channels(id),
    draft_id        INTEGER NOT NULL REFERENCES drafts(id),
    channel_msg_id  INTEGER NOT NULL,
    published_at    TEXT NOT NULL,
    views           INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pub_channel ON published(channel_id);

-- 配套资料。一条素材可以挂多份，频道帖底部的按钮是否出现取决于这里有没有货。
CREATE TABLE IF NOT EXISTS assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL REFERENCES items(id),
    kind            TEXT NOT NULL,            -- link | source | fulltext | vault
    title           TEXT NOT NULL,
    url             TEXT DEFAULT '',
    vault_msg_id    INTEGER DEFAULT 0,        -- vault：资料仓库频道里的消息 id
    passcode        TEXT DEFAULT '',          -- 网盘提取码，必须和链接存一起
    note            TEXT DEFAULT '',
    is_paid         INTEGER DEFAULT 0,        -- 预留：单份资料的付费门槛
    sort            INTEGER DEFAULT 0,
    check_status    TEXT DEFAULT 'unknown',   -- unknown | ok | dead | manual
    last_checked_at TEXT DEFAULT '',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_item ON assets(item_id);

CREATE TABLE IF NOT EXISTS users (
    tg_id         INTEGER PRIMARY KEY,
    username      TEXT DEFAULT '',
    start_payload TEXT DEFAULT '',
    channel_id    INTEGER DEFAULT 0,           -- 从哪个频道来的
    started_at    TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_conn: aiosqlite.Connection | None = None


async def connect() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        _conn = await aiosqlite.connect(settings.db_path)
        _conn.row_factory = aiosqlite.Row
        await _conn.executescript(SCHEMA)
        await _conn.commit()
    return _conn


async def close() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


async def _fetchall(sql: str, args: tuple = ()) -> list[aiosqlite.Row]:
    db = await connect()
    async with db.execute(sql, args) as cur:
        return list(await cur.fetchall())


async def _fetchone(sql: str, args: tuple = ()) -> aiosqlite.Row | None:
    db = await connect()
    async with db.execute(sql, args) as cur:
        return await cur.fetchone()


def _update(table: str, allowed: set[str]):
    """生成一个字段白名单化的 UPDATE helper。"""

    async def _inner(row_id: int, **fields: Any) -> None:
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return
        db = await connect()
        sets = ", ".join(f"{k}=?" for k in data)
        await db.execute(
            f"UPDATE {table} SET {sets} WHERE id=?", (*data.values(), row_id)
        )
        await db.commit()

    return _inner


# ============================================================ bots

BOT_FIELDS = {"name", "role", "token_env_key", "username", "is_active"}
update_bot = _update("bots", BOT_FIELDS)


async def create_bot(
    *, name: str, role: str, token_env_key: str, username: str = ""
) -> int:
    db = await connect()
    cur = await db.execute(
        """INSERT INTO bots (name, role, token_env_key, username, created_at)
           VALUES (?,?,?,?,?)""",
        (name, role, token_env_key, username, _now()),
    )
    await db.commit()
    return int(cur.lastrowid)  # type: ignore[arg-type]


async def get_bot(bot_id: int) -> aiosqlite.Row | None:
    return await _fetchone("SELECT * FROM bots WHERE id=?", (bot_id,))


async def get_bot_by_name(name: str) -> aiosqlite.Row | None:
    return await _fetchone("SELECT * FROM bots WHERE name=?", (name,))


async def list_bots(active_only: bool = False) -> list[aiosqlite.Row]:
    sql = "SELECT * FROM bots"
    if active_only:
        sql += " WHERE is_active=1"
    return await _fetchall(sql + " ORDER BY role, name")


async def delete_bot(bot_id: int) -> None:
    db = await connect()
    await db.execute("DELETE FROM bots WHERE id=?", (bot_id,))
    await db.commit()


# ============================================================ verticals

VERTICAL_FIELDS = {
    "name", "slug", "description", "style_prompt",
    "relevance_threshold", "is_active",
}
update_vertical = _update("verticals", VERTICAL_FIELDS)


async def create_vertical(
    *, name: str, slug: str, description: str = "", style_prompt: str = "",
    relevance_threshold: int = 5,
) -> int:
    db = await connect()
    cur = await db.execute(
        """INSERT INTO verticals
           (name, slug, description, style_prompt, relevance_threshold, created_at)
           VALUES (?,?,?,?,?,?)""",
        (name, slug, description, style_prompt, relevance_threshold, _now()),
    )
    await db.commit()
    return int(cur.lastrowid)  # type: ignore[arg-type]


async def get_vertical(vertical_id: int) -> aiosqlite.Row | None:
    return await _fetchone("SELECT * FROM verticals WHERE id=?", (vertical_id,))


async def get_vertical_by_slug(slug: str) -> aiosqlite.Row | None:
    return await _fetchone("SELECT * FROM verticals WHERE slug=?", (slug,))


async def list_verticals(active_only: bool = False) -> list[aiosqlite.Row]:
    sql = "SELECT * FROM verticals"
    if active_only:
        sql += " WHERE is_active=1"
    return await _fetchall(sql + " ORDER BY name")


async def delete_vertical(vertical_id: int) -> None:
    db = await connect()
    await db.execute("DELETE FROM verticals WHERE id=?", (vertical_id,))
    await db.commit()


# ============================================================ channels

CHANNEL_FIELDS = {
    "name", "chat_id", "username", "publisher_bot_id", "sale_bot_id",
    "linked_group_id", "vertical_id", "publish_cron", "timezone", "is_active",
    "health_status", "health_detail", "health_checked_at",
}
update_channel = _update("channels", CHANNEL_FIELDS)


async def create_channel(
    *, name: str, chat_id: int, vertical_id: int, publisher_bot_id: int,
    sale_bot_id: int | None = None, username: str = "", linked_group_id: int = 0,
    publish_cron: str = "0 9 * * *", timezone_name: str = "Asia/Shanghai",
) -> int:
    db = await connect()
    cur = await db.execute(
        """INSERT INTO channels
           (name, chat_id, username, publisher_bot_id, sale_bot_id,
            linked_group_id, vertical_id, publish_cron, timezone, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (name, chat_id, username, publisher_bot_id, sale_bot_id,
         linked_group_id, vertical_id, publish_cron, timezone_name, _now()),
    )
    await db.commit()
    return int(cur.lastrowid)  # type: ignore[arg-type]


async def get_channel(channel_id: int) -> aiosqlite.Row | None:
    return await _fetchone("SELECT * FROM channels WHERE id=?", (channel_id,))


async def get_channel_by_chat_id(chat_id: int) -> aiosqlite.Row | None:
    return await _fetchone("SELECT * FROM channels WHERE chat_id=?", (chat_id,))


async def list_channels(active_only: bool = False) -> list[aiosqlite.Row]:
    sql = "SELECT * FROM channels"
    if active_only:
        sql += " WHERE is_active=1"
    return await _fetchall(sql + " ORDER BY name")


async def channels_overview() -> list[aiosqlite.Row]:
    """后台频道卡片用：一次查出频道 + 绑定的 bot / 方向 + 队列长度 + 最近发布。"""
    return await _fetchall(
        """SELECT c.*,
                  v.name AS vertical_name, v.slug AS vertical_slug,
                  pb.name AS publisher_name, pb.username AS publisher_username,
                  sb.name AS sale_name, sb.username AS sale_username,
                  (SELECT COUNT(*) FROM queue WHERE channel_id = c.id)
                      AS queue_size,
                  (SELECT COUNT(*) FROM published WHERE channel_id = c.id)
                      AS published_total,
                  (SELECT MAX(published_at) FROM published WHERE channel_id = c.id)
                      AS last_published_at,
                  (SELECT d.title FROM queue q JOIN drafts d ON d.id = q.draft_id
                    WHERE q.channel_id = c.id
                    ORDER BY q.priority DESC, q.created_at ASC LIMIT 1)
                      AS next_title
           FROM channels c
           LEFT JOIN verticals v ON v.id = c.vertical_id
           LEFT JOIN bots pb ON pb.id = c.publisher_bot_id
           LEFT JOIN bots sb ON sb.id = c.sale_bot_id
           ORDER BY c.is_active DESC, c.name"""
    )


async def channels_for_vertical(vertical_id: int) -> list[aiosqlite.Row]:
    return await _fetchall(
        "SELECT * FROM channels WHERE vertical_id=? AND is_active=1 ORDER BY name",
        (vertical_id,),
    )


async def delete_channel(channel_id: int) -> None:
    db = await connect()
    await db.execute("DELETE FROM channels WHERE id=?", (channel_id,))
    await db.commit()


# ============================================================ items

async def create_item(
    *,
    source_type: str,
    raw_text: str,
    source_url: str = "",
    source_title: str = "",
    source_link: str = "",
    media: list[dict[str, Any]] | None = None,
    dedup_key: str = "",
) -> int | None:
    """入库。dedup_key 冲突时返回 None，表示这份素材已经收过。"""
    db = await connect()
    now = _now()
    try:
        cur = await db.execute(
            """INSERT INTO items
               (source_type, source_url, source_title, source_link, raw_text,
                media_json, dedup_key, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                source_type, source_url, source_title, source_link, raw_text,
                json.dumps(media or [], ensure_ascii=False), dedup_key,
                str(ItemStatus.NEW), now, now,
            ),
        )
        await db.commit()
        return cur.lastrowid
    except aiosqlite.IntegrityError:
        return None


async def get_item(item_id: int) -> aiosqlite.Row | None:
    return await _fetchone("SELECT * FROM items WHERE id=?", (item_id,))


async def item_by_dedup_key(key: str) -> aiosqlite.Row | None:
    """按去重键找已有素材。录入前先查一次，好当场告诉人"这条收过了"，
    而不是等后台跑到一半才静悄悄地丢掉。"""
    if not key:
        return None
    return await _fetchone("SELECT * FROM items WHERE dedup_key=?", (key,))


async def update_item(item_id: int, **fields: Any) -> None:
    if not fields:
        return
    db = await connect()
    fields["updated_at"] = _now()
    sets = ", ".join(f"{k}=?" for k in fields)
    await db.execute(
        f"UPDATE items SET {sets} WHERE id=?", (*fields.values(), item_id)
    )
    await db.commit()


async def set_classification(
    item_id: int,
    *,
    vertical_id: int,
    relevance: int,
    tags: list[str],
    level: str,
    reason: str,
    scores: dict[str, int] | None = None,
    keep_status: bool = False,
) -> None:
    """写入路由结果。

    keep_status=True 用于回补历史素材的分类：那些素材早就有草稿、甚至已经
    进了队列，把状态推回"已分类"等于把人工审核的进度抹掉。
    """
    fields: dict[str, Any] = dict(
        vertical_id=vertical_id,
        relevance=relevance,
        topic_tags=json.dumps(tags, ensure_ascii=False),
        suggested_level=level,
        classify_reason=reason,
        route_scores=json.dumps(scores or {}, ensure_ascii=False),
    )
    if not keep_status:
        fields["status"] = str(ItemStatus.CLASSIFIED)
    await update_item(item_id, **fields)


async def list_items(status: str, limit: int = 50) -> list[aiosqlite.Row]:
    return await _fetchall(
        "SELECT * FROM items WHERE status=? ORDER BY id ASC LIMIT ?",
        (status, limit),
    )


async def counts_by_status() -> dict[str, int]:
    rows = await _fetchall("SELECT status, COUNT(*) AS c FROM items GROUP BY status")
    return {r["status"]: int(r["c"]) for r in rows}


async def browse_items(
    *, status: str = "", vertical_id: int = 0, q: str = "",
    limit: int = 20, offset: int = 0,
) -> tuple[list[aiosqlite.Row], int]:
    """后台列表页：状态 / 方向过滤 + 关键词搜索 + 分页。"""
    where: list[str] = []
    args: list[Any] = []
    if status:
        # 支持逗号分隔的多状态，"处理中" 这类聚合筛选靠它（new,classified）
        parts = [s for s in status.split(",") if s]
        if len(parts) == 1:
            where.append("i.status = ?")
            args.append(parts[0])
        elif parts:
            where.append(f"i.status IN ({','.join('?' * len(parts))})")
            args.extend(parts)
    if vertical_id:
        where.append("i.vertical_id = ?")
        args.append(vertical_id)
    if q:
        where.append("(i.raw_text LIKE ? OR i.source_title LIKE ? OR d.title LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like, like])
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    join = """
        LEFT JOIN drafts d ON d.id = (
            SELECT id FROM drafts WHERE item_id = i.id ORDER BY version DESC LIMIT 1
        )
        LEFT JOIN verticals v ON v.id = i.vertical_id
    """
    row = await _fetchone(
        f"SELECT COUNT(*) AS c FROM items i {join} {clause}", tuple(args)
    )
    total = int(row["c"]) if row else 0

    rows = await _fetchall(
        f"""SELECT i.*, d.id AS draft_id, d.title AS draft_title,
                   d.version AS draft_version, d.level AS draft_level,
                   v.name AS vertical_name,
                   (SELECT COUNT(*) FROM drafts WHERE item_id = i.id) AS draft_count,
                   (SELECT COUNT(*) FROM queue WHERE item_id = i.id) AS queue_count
            FROM items i {join} {clause}
            ORDER BY i.id DESC LIMIT ? OFFSET ?""",
        (*args, limit, offset),
    )
    return rows, total


# ============================================================ drafts

async def add_draft(item_id: int, draft: Draft, edited_by: str = "llm") -> int:
    db = await connect()
    row = await _fetchone(
        "SELECT COALESCE(MAX(version), 0) + 1 AS v FROM drafts WHERE item_id=?",
        (item_id,),
    )
    version = int(row["v"])  # type: ignore[index]
    cur = await db.execute(
        """INSERT INTO drafts
           (item_id, channel_id, version, level, title, tldr, body_html, tags,
            attribution, note, revise_note, edited_by, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item_id, draft.channel_id, version, str(draft.level), draft.title,
            draft.tldr, draft.body_html,
            json.dumps(draft.tags, ensure_ascii=False),
            draft.attribution, draft.note, draft.revise_note, edited_by, _now(),
        ),
    )
    await db.commit()
    return int(cur.lastrowid)  # type: ignore[arg-type]


def _row_to_draft(row: aiosqlite.Row) -> Draft:
    return Draft(
        id=row["id"],
        item_id=row["item_id"],
        channel_id=row["channel_id"],
        version=row["version"],
        level=Level(row["level"]),
        title=row["title"],
        tldr=row["tldr"],
        body_html=row["body_html"],
        tags=json.loads(row["tags"]),
        attribution=row["attribution"],
        note=row["note"],
        revise_note=row["revise_note"],
        edited_by=row["edited_by"],
    )


async def get_draft(draft_id: int) -> Draft | None:
    row = await _fetchone("SELECT * FROM drafts WHERE id=?", (draft_id,))
    return _row_to_draft(row) if row else None


async def latest_draft(item_id: int) -> Draft | None:
    row = await _fetchone(
        "SELECT * FROM drafts WHERE item_id=? ORDER BY version DESC LIMIT 1",
        (item_id,),
    )
    return _row_to_draft(row) if row else None


async def list_drafts(item_id: int) -> list[Draft]:
    rows = await _fetchall(
        "SELECT * FROM drafts WHERE item_id=? ORDER BY version ASC", (item_id,)
    )
    return [_row_to_draft(r) for r in rows]


async def draft_ids(item_id: int) -> list[int]:
    rows = await _fetchall(
        "SELECT id FROM drafts WHERE item_id=? ORDER BY version ASC", (item_id,)
    )
    return [int(r["id"]) for r in rows]


async def update_draft(draft_id: int, **fields: Any) -> None:
    """就地修改一版草稿（后台手工编辑用）。

    白名单字段，避免把 item_id / version 改坏。想留历史就走 add_draft
    另存为新版本。
    """
    allowed = {
        "title", "tldr", "body_html", "attribution", "note", "level",
        "channel_id", "edited_by",
    }
    data = {k: v for k, v in fields.items() if k in allowed}
    if "tags" in fields:
        data["tags"] = json.dumps(fields["tags"], ensure_ascii=False)
    if not data:
        return
    db = await connect()
    sets = ", ".join(f"{k}=?" for k in data)
    await db.execute(
        f"UPDATE drafts SET {sets} WHERE id=?", (*data.values(), draft_id)
    )
    await db.commit()


# ============================================================ queue

async def enqueue(
    item_id: int, channel_id: int, draft_id: int,
    priority: int = 0, pin_date: str = "",
) -> None:
    db = await connect()
    await db.execute(
        """INSERT INTO queue
           (item_id, channel_id, draft_id, priority, pin_date, created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(item_id, channel_id) DO UPDATE SET
             draft_id=excluded.draft_id,
             priority=excluded.priority,
             pin_date=excluded.pin_date""",
        (item_id, channel_id, draft_id, priority, pin_date, _now()),
    )
    await db.commit()
    await update_item(item_id, status=str(ItemStatus.APPROVED))


async def pop_next(channel_id: int, today: str) -> aiosqlite.Row | None:
    """取某个频道的下一条待发。

    指定了 pin_date 的只在当天可发且优先；其余按 priority 降序、入队时间升序。
    """
    return await _fetchone(
        """SELECT * FROM queue
           WHERE channel_id = ? AND (pin_date = ? OR pin_date = '')
           ORDER BY (pin_date = ?) DESC, priority DESC, created_at ASC
           LIMIT 1""",
        (channel_id, today, today),
    )


async def dequeue(item_id: int, channel_id: int) -> None:
    db = await connect()
    await db.execute(
        "DELETE FROM queue WHERE item_id=? AND channel_id=?", (item_id, channel_id)
    )
    await db.commit()


async def remove_from_all_queues(item_id: int) -> None:
    db = await connect()
    await db.execute("DELETE FROM queue WHERE item_id=?", (item_id,))
    await db.commit()


async def queue_size(channel_id: int | None = None) -> int:
    if channel_id is None:
        row = await _fetchone("SELECT COUNT(*) AS c FROM queue")
    else:
        row = await _fetchone(
            "SELECT COUNT(*) AS c FROM queue WHERE channel_id=?", (channel_id,)
        )
    return int(row["c"]) if row else 0


async def queue_list(
    channel_id: int | None = None, limit: int = 100
) -> list[aiosqlite.Row]:
    sql = """SELECT q.*, d.title, d.level, d.version,
                    LENGTH(d.body_html) AS chars,
                    c.name AS channel_name, c.username AS channel_username
             FROM queue q
             JOIN drafts d ON d.id = q.draft_id
             JOIN channels c ON c.id = q.channel_id"""
    args: tuple = ()
    if channel_id is not None:
        sql += " WHERE q.channel_id = ?"
        args = (channel_id,)
    sql += " ORDER BY q.channel_id, q.priority DESC, q.created_at ASC LIMIT ?"
    return await _fetchall(sql, (*args, limit))


async def queue_entry(item_id: int, channel_id: int) -> aiosqlite.Row | None:
    return await _fetchone(
        "SELECT * FROM queue WHERE item_id=? AND channel_id=?", (item_id, channel_id)
    )


async def queue_entries_for_item(item_id: int) -> list[aiosqlite.Row]:
    return await _fetchall(
        """SELECT q.*, c.name AS channel_name FROM queue q
           JOIN channels c ON c.id = q.channel_id
           WHERE q.item_id=?""",
        (item_id,),
    )


async def set_queue_fields(item_id: int, channel_id: int, **fields: Any) -> None:
    allowed = {"priority", "pin_date", "draft_id"}
    data = {k: v for k, v in fields.items() if k in allowed}
    if not data:
        return
    db = await connect()
    sets = ", ".join(f"{k}=?" for k in data)
    await db.execute(
        f"UPDATE queue SET {sets} WHERE item_id=? AND channel_id=?",
        (*data.values(), item_id, channel_id),
    )
    await db.commit()


# ============================================================ published

async def mark_published(
    item_id: int, channel_id: int, draft_id: int, msg_id: int
) -> None:
    db = await connect()
    await db.execute(
        """INSERT INTO published
           (item_id, channel_id, draft_id, channel_msg_id, published_at)
           VALUES (?,?,?,?,?)""",
        (item_id, channel_id, draft_id, msg_id, _now()),
    )
    await db.commit()
    await dequeue(item_id, channel_id)
    # 还在别的频道队列里排着就不算发完
    if not await queue_entries_for_item(item_id):
        await update_item(item_id, status=str(ItemStatus.PUBLISHED))


async def published_list(
    channel_id: int | None = None, limit: int = 50
) -> list[aiosqlite.Row]:
    sql = """SELECT p.*, d.title, d.level, c.name AS channel_name,
                    c.username AS channel_username
             FROM published p
             JOIN drafts d ON d.id = p.draft_id
             JOIN channels c ON c.id = p.channel_id"""
    args: tuple = ()
    if channel_id is not None:
        sql += " WHERE p.channel_id = ?"
        args = (channel_id,)
    sql += " ORDER BY p.published_at DESC LIMIT ?"
    return await _fetchall(sql, (*args, limit))


async def published_for_item(item_id: int) -> list[aiosqlite.Row]:
    return await _fetchall(
        """SELECT p.*, c.name AS channel_name, c.username AS channel_username
           FROM published p JOIN channels c ON c.id = p.channel_id
           WHERE p.item_id=? ORDER BY p.published_at DESC""",
        (item_id,),
    )


# ============================================================ assets

ASSET_FIELDS = {
    "kind", "title", "url", "vault_msg_id", "passcode", "note",
    "is_paid", "sort", "check_status", "last_checked_at",
}
update_asset = _update("assets", ASSET_FIELDS)


async def create_asset(
    item_id: int, *, kind: str, title: str, url: str = "",
    passcode: str = "", note: str = "", vault_msg_id: int = 0,
    is_paid: int = 0, sort: int | None = None,
) -> int:
    db = await connect()
    if sort is None:
        row = await _fetchone(
            "SELECT COALESCE(MAX(sort), 0) + 10 AS s FROM assets WHERE item_id=?",
            (item_id,),
        )
        sort = int(row["s"])  # type: ignore[index]
    cur = await db.execute(
        """INSERT INTO assets
           (item_id, kind, title, url, vault_msg_id, passcode, note,
            is_paid, sort, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (item_id, kind, title, url, vault_msg_id, passcode, note,
         is_paid, sort, _now()),
    )
    await db.commit()
    return int(cur.lastrowid)  # type: ignore[arg-type]


async def get_asset(asset_id: int) -> aiosqlite.Row | None:
    return await _fetchone("SELECT * FROM assets WHERE id=?", (asset_id,))


async def list_assets(item_id: int) -> list[aiosqlite.Row]:
    return await _fetchall(
        "SELECT * FROM assets WHERE item_id=? ORDER BY sort, id", (item_id,)
    )


async def asset_count(item_id: int) -> int:
    """频道帖要不要挂「获取完整资料」按钮，就看这个数。"""
    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM assets WHERE item_id=?", (item_id,)
    )
    return int(row["c"]) if row else 0


async def asset_counts(item_ids: list[int]) -> dict[int, int]:
    """列表页批量取，避免 N+1。"""
    if not item_ids:
        return {}
    marks = ",".join("?" * len(item_ids))
    rows = await _fetchall(
        f"SELECT item_id, COUNT(*) AS c FROM assets "
        f"WHERE item_id IN ({marks}) GROUP BY item_id",
        tuple(item_ids),
    )
    return {int(r["item_id"]): int(r["c"]) for r in rows}


async def delete_asset(asset_id: int) -> None:
    db = await connect()
    await db.execute("DELETE FROM assets WHERE id=?", (asset_id,))
    await db.commit()


# ============================================================ users

async def upsert_user(
    tg_id: int, username: str, payload: str, channel_id: int = 0
) -> None:
    db = await connect()
    await db.execute(
        """INSERT INTO users (tg_id, username, start_payload, channel_id, started_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(tg_id) DO UPDATE SET username=excluded.username""",
        (tg_id, username, payload, channel_id, _now()),
    )
    await db.commit()


async def user_count() -> int:
    row = await _fetchone("SELECT COUNT(*) AS c FROM users")
    return int(row["c"]) if row else 0

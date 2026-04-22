from __future__ import annotations

import random
from datetime import datetime

from app.auth import is_owner
from app.core.plugin import CommandPlugin, PluginMeta
from app.db import get_conn

plugin = None


def _ensure_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quote_board (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL DEFAULT 0,
                quote_text TEXT NOT NULL,
                from_user_id INTEGER,
                from_user_name TEXT DEFAULT '',
                created_by INTEGER,
                created_at TEXT NOT NULL DEFAULT ''
            )
            """
        )


_ensure_tables()


def _scope_group_id(ctx) -> int:
    return int(ctx.group_id or 0)


def _is_group_admin(ctx) -> bool:
    return ctx.role in {"admin", "owner"} or is_owner(ctx.user_id)


def _extract_after_command(ctx, command: str) -> str:
    text = (ctx.text or "").strip()
    variants = [command, f"/{command}"] if not command.startswith("/") else [command, command[1:]]
    for variant in variants:
        if text == variant:
            return ""
        prefix = variant + " "
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return ""


def _add_quote(group_id: int, quote_text: str, from_user_id: int | None, from_user_name: str, created_by: int | None) -> int:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO quote_board (group_id, quote_text, from_user_id, from_user_name, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (group_id, quote_text, from_user_id, from_user_name, created_by, now),
        )
        return int(cur.lastrowid)


def _get_random_quote(group_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM quote_board WHERE group_id=? ORDER BY id ASC",
            (group_id,),
        ).fetchall()
    if not rows:
        return None
    return dict(random.choice(rows))


def _list_quotes(group_id: int, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM quote_board WHERE group_id=? ORDER BY id DESC LIMIT ?",
            (group_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def _delete_quote(group_id: int, quote_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM quote_board WHERE group_id=? AND id=?", (group_id, quote_id))
        return cur.rowcount > 0


def _count_quotes(group_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM quote_board WHERE group_id=?", (group_id,)).fetchone()
        return int(row["c"] if row else 0)


quote_help = CommandPlugin(
    name="quote_help",
    command="语录帮助",
    description="show quote board help",
    meta=PluginMeta(name="quote_help", version="1.0.0", author="OpenClaw", description="群聊语录馆帮助"),
)


@quote_help.handle
async def on_quote_help(ctx):
    await ctx.reply(
        "语录馆命令：\n"
        "- 收录语录 一段内容\n"
        "- 今日语录\n"
        "- 随机语录\n"
        "- 语录列表 [数量]\n"
        "- 删除语录 ID（群管理/主人）\n"
        "特点：每个群单独存自己的梗和名场面。"
    )


quote_add = CommandPlugin(
    name="quote_add",
    command="收录语录",
    description="add a group quote",
    meta=PluginMeta(name="quote_add", version="1.0.0", author="OpenClaw", description="收录群聊语录"),
)


@quote_add.handle
async def on_quote_add(ctx):
    content = _extract_after_command(ctx, "收录语录")
    if not content:
        await ctx.reply("用法：收录语录 一段内容")
        return
    sender_name = str((ctx.sender or {}).get("card") or (ctx.sender or {}).get("nickname") or ctx.user_id or "未知成员")
    quote_id = _add_quote(_scope_group_id(ctx), content, ctx.user_id, sender_name, ctx.user_id)
    total = _count_quotes(_scope_group_id(ctx))
    await ctx.reply(f"已收录进语录馆 #{quote_id}\n收录人：{sender_name}\n当前语录数：{total}")


quote_random = CommandPlugin(
    name="quote_random",
    command="随机语录",
    description="show a random quote",
    meta=PluginMeta(name="quote_random", version="1.0.0", author="OpenClaw", description="随机语录"),
)


@quote_random.handle
async def on_quote_random(ctx):
    item = _get_random_quote(_scope_group_id(ctx))
    if not item:
        await ctx.reply("语录馆还是空的，先发：收录语录 一段内容")
        return
    await ctx.reply(
        f"🎙️ 随机语录 #{item['id']}\n"
        f"{item['quote_text']}\n"
        f"—— {item.get('from_user_name') or item.get('from_user_id') or '匿名'}\n"
        f"收录时间：{item.get('created_at') or '-'}"
    )


today_quote = CommandPlugin(
    name="today_quote",
    command="今日语录",
    description="show quote of the day",
    meta=PluginMeta(name="today_quote", version="1.0.0", author="OpenClaw", description="今日语录"),
)


@today_quote.handle
async def on_today_quote(ctx):
    group_id = _scope_group_id(ctx)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM quote_board WHERE group_id=? ORDER BY id ASC", (group_id,)).fetchall()
    if not rows:
        await ctx.reply("今天也没有语录可翻，先收录几条再来。")
        return
    day_seed = int(datetime.utcnow().strftime("%Y%m%d")) + group_id
    item = dict(rows[day_seed % len(rows)])
    await ctx.reply(
        f"📜 今日语录 #{item['id']}\n"
        f"{item['quote_text']}\n"
        f"—— {item.get('from_user_name') or item.get('from_user_id') or '匿名'}"
    )


quote_list = CommandPlugin(
    name="quote_list",
    command="语录列表",
    description="list recent quotes",
    meta=PluginMeta(name="quote_list", version="1.0.0", author="OpenClaw", description="语录列表"),
)


@quote_list.handle
async def on_quote_list(ctx):
    raw = _extract_after_command(ctx, "语录列表")
    limit = 10
    if raw.isdigit():
        limit = max(1, min(20, int(raw)))
    rows = _list_quotes(_scope_group_id(ctx), limit)
    if not rows:
        await ctx.reply("语录馆为空")
        return
    lines = []
    for item in rows:
        text = str(item['quote_text']).replace("\n", " ")
        if len(text) > 28:
            text = text[:28] + "…"
        lines.append(f"#{item['id']} | {item.get('from_user_name') or item.get('from_user_id') or '匿名'} | {text}")
    await ctx.reply("语录馆最近收录：\n" + "\n".join(lines))


quote_delete = CommandPlugin(
    name="quote_delete",
    command="删除语录",
    description="delete quote by id",
    meta=PluginMeta(name="quote_delete", version="1.0.0", author="OpenClaw", description="删除语录"),
)


@quote_delete.handle
async def on_quote_delete(ctx):
    if not _is_group_admin(ctx):
        await ctx.reply("你没有删除语录的权限")
        return
    raw = _extract_after_command(ctx, "删除语录")
    if not raw.isdigit():
        await ctx.reply("用法：删除语录 ID")
        return
    ok = _delete_quote(_scope_group_id(ctx), int(raw))
    await ctx.reply("删除成功" if ok else "未找到该语录")

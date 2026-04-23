from __future__ import annotations

from datetime import datetime, timedelta

from app.core.plugin import CommandPlugin, PluginMeta
from app.db import get_conn


# =========================
# DB
# =========================

def _today_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _ensure_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_message_daily_stats (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                stat_date TEXT NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (group_id, user_id, stat_date)
            )
            """
        )


_ensure_tables()


# =========================
# helpers
# =========================

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _record_group_message(group_id: int, user_id: int) -> None:
    stat_date = _today_local()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO group_message_daily_stats (group_id, user_id, stat_date, message_count, updated_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(group_id, user_id, stat_date)
            DO UPDATE SET
                message_count = group_message_daily_stats.message_count + 1,
                updated_at = excluded.updated_at
            """,
            (group_id, user_id, stat_date, _now()),
        )


def _top_speakers(group_id: int, stat_date: str, limit: int = 3) -> list[tuple[int, int]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT user_id, message_count
            FROM group_message_daily_stats
            WHERE group_id=? AND stat_date=?
            ORDER BY message_count DESC, updated_at ASC, user_id ASC
            LIMIT ?
            """,
            (group_id, stat_date, limit),
        ).fetchall()
    return [(int(r["user_id"]), int(r["message_count"])) for r in rows]


async def process_group_message_stats(ctx) -> None:
    if not ctx.is_group or ctx.group_id is None or ctx.user_id is None:
        return
    text = (ctx.text or "").strip()
    if not text:
        return
    _record_group_message(int(ctx.group_id), int(ctx.user_id))


# =========================
# commands
# =========================

today_top_speakers = CommandPlugin(
    name="today_top_speakers",
    command="今日水群前三",
    description="show today's top 3 group message senders",
    meta=PluginMeta(name="today_top_speakers", version="1.0.0", author="OpenClaw", description="今日水群前三"),
)


@today_top_speakers.handle
async def on_today_top_speakers(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    stat_date = _today_local()
    rows = _top_speakers(int(ctx.group_id), stat_date, limit=3)
    if not rows:
        await ctx.reply("今天还没有统计到群消息")
        return

    lines = [f"今日水群前三（{stat_date}）"]
    medals = ["🥇", "🥈", "🥉"]
    for idx, (user_id, count) in enumerate(rows, start=1):
        medal = medals[idx - 1] if idx <= len(medals) else f"#{idx}"
        lines.append(f"{medal} {user_id}：{count} 条")
    await ctx.reply("\n".join(lines))

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.plugin import CommandPlugin, PluginMeta
from app.db import get_conn

try:
    from user_plugins.cdk_rewards import _claim_cdk
except Exception:  # optional integration
    _claim_cdk = None


# =========================
# DB
# =========================

def _today_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _date_days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_message_reward_settings (
                group_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                first_pool_name TEXT NOT NULL DEFAULT '',
                second_pool_name TEXT NOT NULL DEFAULT '',
                third_pool_name TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        try:
            conn.execute("ALTER TABLE group_message_reward_settings ADD COLUMN first_pool_name TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE group_message_reward_settings ADD COLUMN second_pool_name TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE group_message_reward_settings ADD COLUMN third_pool_name TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_message_reward_runs (
                group_id INTEGER NOT NULL,
                stat_date TEXT NOT NULL,
                rewarded_at TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (group_id, stat_date)
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


def _ensure_reward_settings(group_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO group_message_reward_settings (group_id, updated_at) VALUES (?, ?)",
            (group_id, _now()),
        )


def _get_reward_settings(group_id: int) -> dict:
    _ensure_reward_settings(group_id)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT enabled, first_pool_name, second_pool_name, third_pool_name FROM group_message_reward_settings WHERE group_id=?",
            (group_id,),
        ).fetchone()
    if row is None:
        return {"enabled": 0, "first_pool_name": "", "second_pool_name": "", "third_pool_name": ""}
    return {
        "enabled": int(row["enabled"] or 0),
        "first_pool_name": str(row["first_pool_name"] or ""),
        "second_pool_name": str(row["second_pool_name"] or ""),
        "third_pool_name": str(row["third_pool_name"] or ""),
    }


def _set_reward_settings(
    group_id: int,
    *,
    enabled: int | None = None,
    first_pool_name: str | None = None,
    second_pool_name: str | None = None,
    third_pool_name: str | None = None,
) -> None:
    _ensure_reward_settings(group_id)
    fields: list[str] = []
    params: list[object] = []
    if enabled is not None:
        fields.append("enabled=?")
        params.append(int(enabled))
    if first_pool_name is not None:
        fields.append("first_pool_name=?")
        params.append(str(first_pool_name))
    if second_pool_name is not None:
        fields.append("second_pool_name=?")
        params.append(str(second_pool_name))
    if third_pool_name is not None:
        fields.append("third_pool_name=?")
        params.append(str(third_pool_name))
    fields.append("updated_at=?")
    params.append(_now())
    params.append(group_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE group_message_reward_settings SET {', '.join(fields)} WHERE group_id=?",
            tuple(params),
        )


def _list_enabled_reward_groups() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT group_id, enabled, first_pool_name, second_pool_name, third_pool_name FROM group_message_reward_settings WHERE enabled=1"
        ).fetchall()
    result = []
    for r in rows:
        item = {
            "group_id": int(r["group_id"]),
            "enabled": int(r["enabled"] or 0),
            "first_pool_name": str(r["first_pool_name"] or ""),
            "second_pool_name": str(r["second_pool_name"] or ""),
            "third_pool_name": str(r["third_pool_name"] or ""),
        }
        if item["first_pool_name"] or item["second_pool_name"] or item["third_pool_name"]:
            result.append(item)
    return result


def _reward_already_processed(group_id: int, stat_date: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM group_message_reward_runs WHERE group_id=? AND stat_date=?",
            (group_id, stat_date),
        ).fetchone()
    return row is not None


def _mark_reward_processed(group_id: int, stat_date: str, summary: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO group_message_reward_runs (group_id, stat_date, rewarded_at, summary) VALUES (?, ?, ?, ?)",
            (group_id, stat_date, _now(), summary),
        )


async def _resolve_group_member_name(api, group_id: int, user_id: int) -> str:
    try:
        resp = await api.get_group_member_info(int(group_id), int(user_id), no_cache=False)
        data = resp.get("data") if isinstance(resp, dict) else None
        if isinstance(data, dict):
            card = str(data.get("card") or "").strip()
            nickname = str(data.get("nickname") or "").strip()
            if card:
                return card
            if nickname:
                return nickname
    except Exception:
        pass
    return str(user_id)


async def _render_ranking_lines(api, group_id: int, stat_date: str, rows: list[tuple[int, int]], title: str) -> str:
    lines = [f"{title}（{stat_date}）"]
    medals = ["🥇", "🥈", "🥉"]
    for idx, (user_id, count) in enumerate(rows, start=1):
        medal = medals[idx - 1] if idx <= len(medals) else f"#{idx}"
        name = await _resolve_group_member_name(api, group_id, user_id)
        lines.append(f"{medal} {name}（{user_id}）：{count} 条")
    return "\n".join(lines)


async def process_group_message_stats(ctx) -> None:
    if not ctx.is_group or ctx.group_id is None or ctx.user_id is None:
        return
    text = (ctx.text or "").strip()
    if not text:
        return
    _record_group_message(int(ctx.group_id), int(ctx.user_id))


async def process_group_message_reward_tick(api) -> None:
    if _claim_cdk is None:
        return
    stat_date = _date_days_ago(1)
    now = datetime.now()
    # avoid midnight race / partial stats: process after 00:05 local time
    if now.hour == 0 and now.minute < 5:
        return

    for item in _list_enabled_reward_groups():
        group_id = int(item["group_id"])
        if _reward_already_processed(group_id, stat_date):
            continue

        rows = _top_speakers(group_id, stat_date, limit=3)
        if not rows:
            _mark_reward_processed(group_id, stat_date, "no-stats")
            continue

        summary_parts: list[str] = []
        group_notices: list[str] = [f"昨日水群前三奖励（{stat_date}）"]
        medals = ["🥇", "🥈", "🥉"]
        rank_pools = {
            1: str(item.get("first_pool_name") or ""),
            2: str(item.get("second_pool_name") or ""),
            3: str(item.get("third_pool_name") or ""),
        }

        for idx, (user_id, count) in enumerate(rows, start=1):
            medal = medals[idx - 1] if idx <= len(medals) else f"#{idx}"
            pool_name = rank_pools.get(idx, "")
            name = await _resolve_group_member_name(api, group_id, user_id)
            if not pool_name:
                group_notices.append(f"{medal} {name}：未配置第 {idx} 名奖励卡池")
                summary_parts.append(f"{idx}:{user_id}:no_pool")
                continue
            cdk = _claim_cdk(group_id, pool_name, int(user_id), "daily_top_speakers", f"{stat_date}:{idx}")
            if cdk == "":
                group_notices.append(f"{medal} {name}：卡池 {pool_name} 已空")
                summary_parts.append(f"{idx}:{user_id}:empty")
                continue
            if cdk is None:
                group_notices.append(f"{medal} {name}：今日已发过同类奖励")
                summary_parts.append(f"{idx}:{user_id}:duplicate")
                continue
            try:
                try:
                    await api.send_temp_msg(group_id, int(user_id), f"水群排行奖励已发放\n群号：{group_id}\n排名：第 {idx} 名\n日期：{stat_date}\n奖励卡池：{pool_name}\nCDK：{cdk}")
                except Exception:
                    await api.send_private_msg(int(user_id), f"水群排行奖励已发放\n群号：{group_id}\n排名：第 {idx} 名\n日期：{stat_date}\n奖励卡池：{pool_name}\nCDK：{cdk}")
                group_notices.append(f"{medal} {name}：奖励已私发（{pool_name}）")
                summary_parts.append(f"{idx}:{user_id}:ok:{pool_name}")
            except Exception:
                group_notices.append(f"{medal} {name}：奖励发放失败，请检查私聊权限")
                summary_parts.append(f"{idx}:{user_id}:send_fail")

        try:
            await api.send_group_msg(group_id, "\n".join(group_notices))
        except Exception:
            pass
        _mark_reward_processed(group_id, stat_date, ";".join(summary_parts) or "done")


# =========================
# commands
# =========================

water_reward_enable = CommandPlugin(
    name="water_reward_enable",
    command="开启水群前三奖励",
    description="enable daily top3 message reward",
    meta=PluginMeta(name="water_reward_enable", version="1.0.0", author="OpenClaw", description="开启水群前三奖励"),
)


@water_reward_enable.handle
async def on_water_reward_enable(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    arg = (ctx.text or "").replace("开启水群前三奖励", "", 1).strip()
    parts = [x for x in arg.split() if x]
    if len(parts) != 3:
        await ctx.reply("用法：开启水群前三奖励 第一名卡池 第二名卡池 第三名卡池")
        return
    _set_reward_settings(
        int(ctx.group_id),
        enabled=1,
        first_pool_name=parts[0],
        second_pool_name=parts[1],
        third_pool_name=parts[2],
    )
    await ctx.reply(
        "已开启每日水群前三自动奖励\n"
        f"第一名卡池：{parts[0]}\n"
        f"第二名卡池：{parts[1]}\n"
        f"第三名卡池：{parts[2]}\n"
        "说明：每天会按昨日水群前三分开发放"
    )


water_reward_disable = CommandPlugin(
    name="water_reward_disable",
    command="关闭水群前三奖励",
    description="disable daily top3 message reward",
    meta=PluginMeta(name="water_reward_disable", version="1.0.0", author="OpenClaw", description="关闭水群前三奖励"),
)


@water_reward_disable.handle
async def on_water_reward_disable(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    _set_reward_settings(int(ctx.group_id), enabled=0)
    await ctx.reply("已关闭每日水群前三自动奖励")


water_reward_status = CommandPlugin(
    name="water_reward_status",
    command="水群前三奖励状态",
    description="show daily top3 message reward status",
    meta=PluginMeta(name="water_reward_status", version="1.0.0", author="OpenClaw", description="水群前三奖励状态"),
)


@water_reward_status.handle
async def on_water_reward_status(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    cfg = _get_reward_settings(int(ctx.group_id))
    lines = [
        "水群前三奖励状态",
        f"启用：{'是' if int(cfg.get('enabled') or 0) == 1 else '否'}",
        f"第一名卡池：{cfg.get('first_pool_name') or '未设置'}",
        f"第二名卡池：{cfg.get('second_pool_name') or '未设置'}",
        f"第三名卡池：{cfg.get('third_pool_name') or '未设置'}",
        "发放逻辑：每天按昨日水群前三分开发放",
    ]
    await ctx.reply("\n".join(lines))


today_top_speakers = CommandPlugin(
    name="today_top_speakers",
    command="今日水群前三",
    description="show today's top 3 group message senders",
    meta=PluginMeta(name="today_top_speakers", version="1.1.0", author="OpenClaw", description="今日水群前三"),
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
    await ctx.reply(await _render_ranking_lines(ctx.api, int(ctx.group_id), stat_date, rows, "今日水群前三"))


yesterday_top_speakers = CommandPlugin(
    name="yesterday_top_speakers",
    command="昨日水群前三",
    description="show yesterday's top 3 group message senders",
    meta=PluginMeta(name="yesterday_top_speakers", version="1.0.0", author="OpenClaw", description="昨日水群前三"),
)


@yesterday_top_speakers.handle
async def on_yesterday_top_speakers(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    stat_date = _date_days_ago(1)
    rows = _top_speakers(int(ctx.group_id), stat_date, limit=3)
    if not rows:
        await ctx.reply("昨天还没有统计到群消息")
        return
    await ctx.reply(await _render_ranking_lines(ctx.api, int(ctx.group_id), stat_date, rows, "昨日水群前三"))


today_message_rank = CommandPlugin(
    name="today_message_rank",
    command="今日水群排行",
    description="show today's group message ranking",
    meta=PluginMeta(name="today_message_rank", version="1.0.0", author="OpenClaw", description="今日水群排行"),
)


@today_message_rank.handle
async def on_today_message_rank(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    stat_date = _today_local()
    rows = _top_speakers(int(ctx.group_id), stat_date, limit=10)
    if not rows:
        await ctx.reply("今天还没有统计到群消息")
        return
    await ctx.reply(await _render_ranking_lines(ctx.api, int(ctx.group_id), stat_date, rows, "今日水群排行 Top10"))

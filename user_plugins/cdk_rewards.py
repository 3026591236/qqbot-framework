from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.auth import is_owner
from app.core.plugin import CommandPlugin, PluginMeta
from app.db import _ensure_column, get_conn

plugin = None


# =========================
# DB
# =========================

def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _ensure_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cdk_reward_admins (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                added_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (group_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cdk_reward_settings (
                group_id INTEGER PRIMARY KEY,
                first_day_pool TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cdk_reward_streak_rules (
                group_id INTEGER NOT NULL,
                streak_days INTEGER NOT NULL,
                pool_name TEXT NOT NULL,
                PRIMARY KEY (group_id, streak_days)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cdk_reward_invite_rules (
                group_id INTEGER NOT NULL,
                invite_count INTEGER NOT NULL,
                pool_name TEXT NOT NULL,
                PRIMARY KEY (group_id, invite_count)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cdk_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                pool_name TEXT NOT NULL,
                cdk_code TEXT NOT NULL,
                added_by INTEGER NOT NULL DEFAULT 0,
                added_at TEXT NOT NULL DEFAULT '',
                claimed_by INTEGER DEFAULT NULL,
                claimed_at TEXT DEFAULT NULL,
                claim_reason TEXT NOT NULL DEFAULT '',
                rule_key TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 1,
                used_count INTEGER NOT NULL DEFAULT 0,
                reusable INTEGER NOT NULL DEFAULT 0,
                UNIQUE(group_id, pool_name, cdk_code)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cdk_reward_logs (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reward_type TEXT NOT NULL,
                rule_key TEXT NOT NULL,
                pool_name TEXT NOT NULL DEFAULT '',
                cdk_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (group_id, user_id, reward_type, rule_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invite_records (
                group_id INTEGER NOT NULL,
                invited_user_id INTEGER NOT NULL,
                inviter_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (group_id, invited_user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invite_stats (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                invite_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (group_id, user_id)
            )
            """
        )
        _ensure_column(conn, "cdk_pool", "quantity", "quantity INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "cdk_pool", "used_count", "used_count INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "cdk_pool", "reusable", "reusable INTEGER NOT NULL DEFAULT 0")


_ensure_tables()


# =========================
# helpers
# =========================

def _extract_target_user_id(ctx):
    event = ctx.raw_event or {}
    for seg in event.get("message", []) if isinstance(event.get("message"), list) else []:
        if isinstance(seg, dict) and seg.get("type") == "at":
            data = seg.get("data") or {}
            qq = data.get("qq")
            if qq and str(qq).isdigit():
                return int(qq)
    for token in ctx.text.split():
        token = token.strip()
        if token.startswith("@") and token[1:].isdigit():
            return int(token[1:])
        if token.isdigit() and len(token) >= 5:
            return int(token)
    return None


def _is_group_admin(ctx) -> bool:
    return ctx.role in {"admin", "owner"} or is_owner(ctx.user_id)


def _extract_after_command(ctx, command: str) -> str:
    text = ctx.text.strip()
    variants = [command, f"/{command}"] if not command.startswith("/") else [command, command[1:]]
    for variant in variants:
        if text == variant:
            return ""
        prefix = variant + " "
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return ""


def _is_reward_admin_for_group(group_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    if is_owner(user_id):
        return True
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM cdk_reward_admins WHERE group_id=? AND user_id=?",
            (group_id, int(user_id)),
        ).fetchone()
        return row is not None


def _ensure_group_settings(group_id: int) -> None:
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO cdk_reward_settings (group_id) VALUES (?)", (group_id,))


def _get_first_day_pool(group_id: int) -> str:
    _ensure_group_settings(group_id)
    with get_conn() as conn:
        row = conn.execute("SELECT first_day_pool FROM cdk_reward_settings WHERE group_id=?", (group_id,)).fetchone()
        return str(row["first_day_pool"]) if row is not None else ""


def _set_first_day_pool(group_id: int, pool_name: str) -> None:
    _ensure_group_settings(group_id)
    with get_conn() as conn:
        conn.execute("UPDATE cdk_reward_settings SET first_day_pool=? WHERE group_id=?", (pool_name, group_id))


def _add_reward_admin(group_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO cdk_reward_admins (group_id, user_id, added_at) VALUES (?, ?, ?)",
            (group_id, user_id, _now()),
        )


def _remove_reward_admin(group_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM cdk_reward_admins WHERE group_id=? AND user_id=?", (group_id, user_id))


def _list_reward_admins(group_id: int) -> list[int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id FROM cdk_reward_admins WHERE group_id=? ORDER BY user_id ASC",
            (group_id,),
        ).fetchall()
        return [int(r["user_id"]) for r in rows]


def _set_streak_rule(group_id: int, streak_days: int, pool_name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cdk_reward_streak_rules (group_id, streak_days, pool_name) VALUES (?, ?, ?) "
            "ON CONFLICT(group_id, streak_days) DO UPDATE SET pool_name=excluded.pool_name",
            (group_id, streak_days, pool_name),
        )


def _remove_streak_rule(group_id: int, streak_days: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM cdk_reward_streak_rules WHERE group_id=? AND streak_days=?", (group_id, streak_days))


def _list_streak_rules(group_id: int) -> list[tuple[int, str]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT streak_days, pool_name FROM cdk_reward_streak_rules WHERE group_id=? ORDER BY streak_days ASC",
            (group_id,),
        ).fetchall()
        return [(int(r["streak_days"]), str(r["pool_name"])) for r in rows]


def _set_invite_rule(group_id: int, invite_count: int, pool_name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cdk_reward_invite_rules (group_id, invite_count, pool_name) VALUES (?, ?, ?) "
            "ON CONFLICT(group_id, invite_count) DO UPDATE SET pool_name=excluded.pool_name",
            (group_id, invite_count, pool_name),
        )


def _remove_invite_rule(group_id: int, invite_count: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM cdk_reward_invite_rules WHERE group_id=? AND invite_count=?", (group_id, invite_count))


def _list_invite_rules(group_id: int) -> list[tuple[int, str]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT invite_count, pool_name FROM cdk_reward_invite_rules WHERE group_id=? ORDER BY invite_count ASC",
            (group_id,),
        ).fetchall()
        return [(int(r["invite_count"]), str(r["pool_name"])) for r in rows]


def _add_cdk(group_id: int, pool_name: str, cdk_code: str, added_by: int | None, *, reusable: bool = False) -> bool:
    try:
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id, quantity, reusable FROM cdk_pool WHERE group_id=? AND pool_name=? AND cdk_code=?",
                (group_id, pool_name, cdk_code),
            ).fetchone()
            if existing is not None:
                if reusable:
                    conn.execute(
                        "UPDATE cdk_pool SET reusable=1, added_by=?, added_at=? WHERE id=?",
                        (int(added_by or 0), _now(), int(existing["id"])),
                    )
                else:
                    conn.execute(
                        "UPDATE cdk_pool SET quantity=?, reusable=0, added_by=?, added_at=? WHERE id=?",
                        (int(existing["quantity"] or 1) + 1, int(added_by or 0), _now(), int(existing["id"])),
                    )
            else:
                conn.execute(
                    "INSERT INTO cdk_pool (group_id, pool_name, cdk_code, added_by, added_at, quantity, used_count, reusable) VALUES (?, ?, ?, ?, ?, 1, 0, ?)",
                    (group_id, pool_name, cdk_code, int(added_by or 0), _now(), 1 if reusable else 0),
                )
        return True
    except Exception:
        return False


def _claim_cdk(group_id: int, pool_name: str, user_id: int, reward_type: str, rule_key: str) -> Optional[str]:
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT cdk_code FROM cdk_reward_logs WHERE group_id=? AND user_id=? AND reward_type=? AND rule_key=?",
            (group_id, user_id, reward_type, rule_key),
        ).fetchone()
        if existing:
            return None

        row = conn.execute(
            "SELECT id, cdk_code, quantity, used_count, reusable FROM cdk_pool WHERE group_id=? AND pool_name=? AND (reusable=1 OR used_count < quantity) ORDER BY reusable DESC, id ASC LIMIT 1",
            (group_id, pool_name),
        ).fetchone()
        if row is None:
            return ""

        cdk_id = int(row["id"])
        cdk_code = str(row["cdk_code"])
        reusable = int(row["reusable"] or 0) == 1
        now = _now()
        if reusable:
            conn.execute(
                "UPDATE cdk_pool SET used_count=used_count+1, claimed_by=?, claimed_at=?, claim_reason=?, rule_key=? WHERE id=?",
                (user_id, now, reward_type, rule_key, cdk_id),
            )
        else:
            next_used = int(row["used_count"] or 0) + 1
            conn.execute(
                "UPDATE cdk_pool SET used_count=?, claimed_by=?, claimed_at=?, claim_reason=?, rule_key=? WHERE id=? AND used_count < quantity",
                (next_used, user_id, now, reward_type, rule_key, cdk_id),
            )
        updated = conn.total_changes
        if updated <= 0:
            return ""
        conn.execute(
            "INSERT INTO cdk_reward_logs (group_id, user_id, reward_type, rule_key, pool_name, cdk_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (group_id, user_id, reward_type, rule_key, pool_name, cdk_code, now),
        )
        return cdk_code


def _pool_stats(group_id: int, pool_name: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if pool_name:
            rows = conn.execute(
                "SELECT pool_name, SUM(CASE WHEN reusable=1 THEN 1 ELSE quantity END) AS total, "
                "SUM(CASE WHEN reusable=1 THEN 999999999 ELSE quantity - used_count END) AS available, "
                "SUM(used_count) AS used, MAX(reusable) AS has_reusable FROM cdk_pool WHERE group_id=? AND pool_name=? GROUP BY pool_name ORDER BY pool_name ASC",
                (group_id, pool_name),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT pool_name, SUM(CASE WHEN reusable=1 THEN 1 ELSE quantity END) AS total, "
                "SUM(CASE WHEN reusable=1 THEN 999999999 ELSE quantity - used_count END) AS available, "
                "SUM(used_count) AS used, MAX(reusable) AS has_reusable FROM cdk_pool WHERE group_id=? GROUP BY pool_name ORDER BY pool_name ASC",
                (group_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def _record_invite(group_id: int, inviter_user_id: int, invited_user_id: int) -> tuple[bool, int]:
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT inviter_user_id FROM invite_records WHERE group_id=? AND invited_user_id=?",
            (group_id, invited_user_id),
        ).fetchone()
        if existing is not None:
            row = conn.execute(
                "SELECT invite_count FROM invite_stats WHERE group_id=? AND user_id=?",
                (group_id, inviter_user_id),
            ).fetchone()
            return False, int(row["invite_count"]) if row else 0

        now = _now()
        conn.execute(
            "INSERT INTO invite_records (group_id, invited_user_id, inviter_user_id, created_at) VALUES (?, ?, ?, ?)",
            (group_id, invited_user_id, inviter_user_id, now),
        )
        row = conn.execute(
            "SELECT invite_count FROM invite_stats WHERE group_id=? AND user_id=?",
            (group_id, inviter_user_id),
        ).fetchone()
        if row is None:
            count = 1
            conn.execute(
                "INSERT INTO invite_stats (group_id, user_id, invite_count, updated_at) VALUES (?, ?, ?, ?)",
                (group_id, inviter_user_id, count, now),
            )
        else:
            count = int(row["invite_count"] or 0) + 1
            conn.execute(
                "UPDATE invite_stats SET invite_count=?, updated_at=? WHERE group_id=? AND user_id=?",
                (count, now, group_id, inviter_user_id),
            )
        return True, count


def _get_invite_count(group_id: int, user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT invite_count FROM invite_stats WHERE group_id=? AND user_id=?",
            (group_id, user_id),
        ).fetchone()
        return int(row["invite_count"]) if row else 0


# =========================
# reward hooks
# =========================

async def process_checkin_reward(ctx, result: dict) -> None:
    if not result.get("ok") or result.get("already"):
        return
    if ctx.group_id is None or ctx.user_id is None:
        return

    user_id = int(ctx.user_id)
    group_id = int(ctx.group_id)
    notices: list[str] = []

    first_day_pool = _get_first_day_pool(group_id)
    if first_day_pool and int(result.get("total_checkins") or 0) == 1:
        cdk = _claim_cdk(group_id, first_day_pool, user_id, "checkin_first_day", "day1")
        if cdk == "":
            notices.append("首日签到奖励卡池已空")
        elif cdk:
            # Prefer temporary-session message (works even if not friends) when possible.
            try:
                await ctx.api.send_temp_msg(
                    group_id,
                    user_id,
                    f"签到奖励已发放\n群号：{group_id}\n类型：首日签到\nCDK：{cdk}",
                )
            except Exception:
                await ctx.api.send_private_msg(
                    user_id,
                    f"签到奖励已发放\n群号：{group_id}\n类型：首日签到\nCDK：{cdk}",
                )
            notices.append("首日签到奖励已私发")

    streak = int(result.get("streak") or 0)
    for days, pool_name in _list_streak_rules(group_id):
        if streak < days:
            continue
        cdk = _claim_cdk(group_id, pool_name, user_id, "checkin_streak", str(days))
        if cdk == "":
            notices.append(f"连签 {days} 天奖励卡池已空")
        elif cdk:
            try:
                await ctx.api.send_temp_msg(
                    group_id,
                    user_id,
                    f"签到奖励已发放\n群号：{group_id}\n类型：连续签到 {days} 天\nCDK：{cdk}",
                )
            except Exception:
                await ctx.api.send_private_msg(
                    user_id,
                    f"签到奖励已发放\n群号：{group_id}\n类型：连续签到 {days} 天\nCDK：{cdk}",
                )
            notices.append(f"连签 {days} 天奖励已私发")

    if notices:
        await ctx.reply("\n".join(notices))


async def process_invite_reward(api, event: dict) -> bool:
    if event.get("post_type") != "notice":
        return False
    if event.get("notice_type") != "group_increase":
        return False

    group_id = event.get("group_id")
    invited_user_id = event.get("user_id")
    inviter_user_id = event.get("operator_id")
    if not group_id or not invited_user_id or not inviter_user_id:
        return False
    if int(invited_user_id) == int(inviter_user_id):
        return False

    inserted, invite_count = _record_invite(int(group_id), int(inviter_user_id), int(invited_user_id))
    if not inserted:
        return False

    notices: list[str] = []
    for need_count, pool_name in _list_invite_rules(int(group_id)):
        if invite_count < need_count:
            continue
        cdk = _claim_cdk(int(group_id), pool_name, int(inviter_user_id), "invite_count", str(need_count))
        if cdk == "":
            notices.append(f"邀请满 {need_count} 人奖励卡池已空")
        elif cdk:
            try:
                try:
                    await api.send_temp_msg(
                        int(group_id),
                        int(inviter_user_id),
                        f"邀请奖励已发放\n群号：{group_id}\n已邀请：{invite_count} 人\n达成条件：{need_count} 人\nCDK：{cdk}",
                    )
                except Exception:
                    await api.send_private_msg(
                        int(inviter_user_id),
                        f"邀请奖励已发放\n群号：{group_id}\n已邀请：{invite_count} 人\n达成条件：{need_count} 人\nCDK：{cdk}",
                    )
                notices.append(f"邀请满 {need_count} 人奖励已私发给 {inviter_user_id}")
            except Exception:
                notices.append(f"邀请满 {need_count} 人奖励发放失败，请检查私聊权限")

    if notices:
        try:
            await api.send_group_msg(int(group_id), "\n".join(notices))
        except Exception:
            pass
    return True


# =========================
# commands
# =========================

reward_help = CommandPlugin(
    name="reward_help",
    command="发卡帮助",
    description="show reward plugin help",
    meta=PluginMeta(name="reward_help", version="1.0.0", author="OpenClaw", description="发卡奖励插件帮助"),
)


@reward_help.handle
async def on_reward_help(ctx):
    await ctx.reply(
        "发卡奖励插件命令\n"
        "- 设置发卡管理员 @QQ/QQ号\n"
        "- 删除发卡管理员 @QQ/QQ号\n"
        "- 发卡管理员列表\n"
        "- 设置签到首日奖励 卡池名/关闭\n"
        "- 设置连续签到奖励 天数 卡池名\n"
        "- 删除连续签到奖励 天数\n"
        "- 设置邀请奖励 人数 卡池名\n"
        "- 删除邀请奖励 人数\n"
        "- 添加CDK 卡池名 CDK（群内）\n"
        "- 添加CDK 群号 卡池名 CDK（私聊）\n"
        "- 卡池状态 [卡池名]\n"
        "- 邀请统计 [@QQ/QQ号]\n"
        "\n"
        "说明：同一个卡池下，重复添加相同 CDK 会自动累计库存，可重复发放。"
    )


set_reward_admin = CommandPlugin(
    name="set_reward_admin",
    command="设置发卡管理员",
    description="set cdk reward admin",
    meta=PluginMeta(name="set_reward_admin", version="1.0.0", author="OpenClaw", description="设置发卡管理员"),
)


@set_reward_admin.handle
async def on_set_reward_admin(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("只有群管理员或机器人主人可以设置发卡管理员")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("请使用 @成员 或 QQ号")
        return
    _add_reward_admin(int(ctx.group_id), int(target))
    await ctx.reply(f"已设置发卡管理员：{target}")


remove_reward_admin = CommandPlugin(
    name="remove_reward_admin",
    command="删除发卡管理员",
    description="remove cdk reward admin",
    meta=PluginMeta(name="remove_reward_admin", version="1.0.0", author="OpenClaw", description="删除发卡管理员"),
)


@remove_reward_admin.handle
async def on_remove_reward_admin(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("只有群管理员或机器人主人可以删除发卡管理员")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("请使用 @成员 或 QQ号")
        return
    _remove_reward_admin(int(ctx.group_id), int(target))
    await ctx.reply(f"已删除发卡管理员：{target}")


reward_admin_list = CommandPlugin(
    name="reward_admin_list",
    command="发卡管理员列表",
    description="list cdk reward admins",
    meta=PluginMeta(name="reward_admin_list", version="1.0.0", author="OpenClaw", description="发卡管理员列表"),
)


@reward_admin_list.handle
async def on_reward_admin_list(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    admins = _list_reward_admins(int(ctx.group_id))
    if not admins:
        await ctx.reply("当前还没有设置发卡管理员")
        return
    await ctx.reply("发卡管理员列表\n" + "\n".join(str(x) for x in admins))


set_first_day_reward = CommandPlugin(
    name="set_first_day_reward",
    command="设置签到首日奖励",
    description="set first day checkin reward pool",
    meta=PluginMeta(name="set_first_day_reward", version="1.0.0", author="OpenClaw", description="设置签到首日奖励"),
)


@set_first_day_reward.handle
async def on_set_first_day_reward(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    if not (_is_group_admin(ctx) or _is_reward_admin_for_group(int(ctx.group_id), ctx.user_id)):
        await ctx.reply("只有群管理员、机器人主人或发卡管理员可以设置")
        return
    arg = _extract_after_command(ctx, "设置签到首日奖励")
    if not arg:
        await ctx.reply("用法：设置签到首日奖励 卡池名/关闭")
        return
    if arg in {"关闭", "off", "OFF", "none", "无"}:
        _set_first_day_pool(int(ctx.group_id), "")
        await ctx.reply("已关闭首日签到 CDK 奖励")
        return
    _set_first_day_pool(int(ctx.group_id), arg)
    await ctx.reply(f"已设置首日签到奖励卡池：{arg}")


set_streak_reward = CommandPlugin(
    name="set_streak_reward",
    command="设置连续签到奖励",
    description="set streak reward rule",
    meta=PluginMeta(name="set_streak_reward", version="1.0.0", author="OpenClaw", description="设置连续签到奖励"),
)


@set_streak_reward.handle
async def on_set_streak_reward(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    if not (_is_group_admin(ctx) or _is_reward_admin_for_group(int(ctx.group_id), ctx.user_id)):
        await ctx.reply("只有群管理员、机器人主人或发卡管理员可以设置")
        return
    parts = _extract_after_command(ctx, "设置连续签到奖励").split(maxsplit=1)
    if len(parts) < 2 or not parts[0].isdigit():
        await ctx.reply("用法：设置连续签到奖励 天数 卡池名")
        return
    days = int(parts[0])
    if days <= 0:
        await ctx.reply("天数必须大于 0")
        return
    _set_streak_rule(int(ctx.group_id), days, parts[1].strip())
    await ctx.reply(f"已设置连续签到 {days} 天奖励卡池：{parts[1].strip()}")


del_streak_reward = CommandPlugin(
    name="del_streak_reward",
    command="删除连续签到奖励",
    description="remove streak reward rule",
    meta=PluginMeta(name="del_streak_reward", version="1.0.0", author="OpenClaw", description="删除连续签到奖励"),
)


@del_streak_reward.handle
async def on_del_streak_reward(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    if not (_is_group_admin(ctx) or _is_reward_admin_for_group(int(ctx.group_id), ctx.user_id)):
        await ctx.reply("只有群管理员、机器人主人或发卡管理员可以设置")
        return
    arg = _extract_after_command(ctx, "删除连续签到奖励")
    if not arg.isdigit():
        await ctx.reply("用法：删除连续签到奖励 天数")
        return
    _remove_streak_rule(int(ctx.group_id), int(arg))
    await ctx.reply(f"已删除连续签到 {arg} 天奖励规则")


set_invite_reward = CommandPlugin(
    name="set_invite_reward",
    command="设置邀请奖励",
    description="set invite reward rule",
    meta=PluginMeta(name="set_invite_reward", version="1.0.0", author="OpenClaw", description="设置邀请奖励"),
)


@set_invite_reward.handle
async def on_set_invite_reward(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    if not (_is_group_admin(ctx) or _is_reward_admin_for_group(int(ctx.group_id), ctx.user_id)):
        await ctx.reply("只有群管理员、机器人主人或发卡管理员可以设置")
        return
    parts = _extract_after_command(ctx, "设置邀请奖励").split(maxsplit=1)
    if len(parts) < 2 or not parts[0].isdigit():
        await ctx.reply("用法：设置邀请奖励 人数 卡池名")
        return
    need = int(parts[0])
    if need <= 0:
        await ctx.reply("人数必须大于 0")
        return
    _set_invite_rule(int(ctx.group_id), need, parts[1].strip())
    await ctx.reply(f"已设置邀请满 {need} 人奖励卡池：{parts[1].strip()}")


del_invite_reward = CommandPlugin(
    name="del_invite_reward",
    command="删除邀请奖励",
    description="remove invite reward rule",
    meta=PluginMeta(name="del_invite_reward", version="1.0.0", author="OpenClaw", description="删除邀请奖励"),
)


@del_invite_reward.handle
async def on_del_invite_reward(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    if not (_is_group_admin(ctx) or _is_reward_admin_for_group(int(ctx.group_id), ctx.user_id)):
        await ctx.reply("只有群管理员、机器人主人或发卡管理员可以设置")
        return
    arg = _extract_after_command(ctx, "删除邀请奖励")
    if not arg.isdigit():
        await ctx.reply("用法：删除邀请奖励 人数")
        return
    _remove_invite_rule(int(ctx.group_id), int(arg))
    await ctx.reply(f"已删除邀请满 {arg} 人奖励规则")


add_cdk = CommandPlugin(
    name="add_cdk",
    command="添加CDK",
    description="add cdk to pool",
    meta=PluginMeta(name="add_cdk", version="1.0.0", author="OpenClaw", description="添加CDK"),
)


@add_cdk.handle
async def on_add_cdk(ctx):
    raw = _extract_after_command(ctx, "添加CDK")
    reusable = False
    for prefix in ("公共 ", "可重复 ", "无限 "):
        if raw.startswith(prefix):
            reusable = True
            raw = raw[len(prefix):].strip()
            break

    parts = raw.split(maxsplit=2)
    target_group_id: Optional[int] = None
    pool_name = ""
    code = ""

    if ctx.is_group and ctx.group_id is not None:
        if len(parts) < 2:
            await ctx.reply("用法：添加CDK [公共] 卡池名 CDK")
            return
        target_group_id = int(ctx.group_id)
        pool_name = parts[0].strip()
        code = parts[1].strip() if len(parts) == 2 else parts[1].strip() + " " + parts[2].strip()
    else:
        if len(parts) < 3 or not parts[0].isdigit():
            await ctx.reply("私聊用法：添加CDK 群号 [公共] 卡池名 CDK")
            return
        target_group_id = int(parts[0])
        remain = raw[len(parts[0]):].strip()
        if remain.startswith("公共 ") or remain.startswith("可重复 ") or remain.startswith("无限 "):
            reusable = True
            remain = remain.split(maxsplit=1)[1].strip()
        remain_parts = remain.split(maxsplit=1)
        if len(remain_parts) < 2:
            await ctx.reply("私聊用法：添加CDK 群号 [公共] 卡池名 CDK")
            return
        pool_name = remain_parts[0].strip()
        code = remain_parts[1].strip()

    if not pool_name or not code:
        await ctx.reply("卡池名和 CDK 不能为空")
        return

    if ctx.is_group:
        if not (_is_group_admin(ctx) or _is_reward_admin_for_group(target_group_id, ctx.user_id)):
            await ctx.reply("只有群管理员、机器人主人或发卡管理员可以添加 CDK")
            return
    else:
        if not _is_reward_admin_for_group(target_group_id, ctx.user_id):
            await ctx.reply("只有机器人主人或该群发卡管理员可以私聊添加 CDK")
            return

    ok = _add_cdk(target_group_id, pool_name, code, ctx.user_id, reusable=reusable)
    if not ok:
        await ctx.reply("添加失败，请检查参数或稍后重试")
        return
    if reusable:
        await ctx.reply(f"已添加公共 CDK 到卡池：{pool_name}\n说明：这张卡添加一次后可重复发放")
    else:
        await ctx.reply(f"已添加 CDK 到卡池：{pool_name}\n说明：普通卡密发出一次会消耗一次库存")


pool_status = CommandPlugin(
    name="pool_status",
    command="卡池状态",
    description="show cdk pool status",
    meta=PluginMeta(name="pool_status", version="1.0.0", author="OpenClaw", description="查看卡池状态"),
)


@pool_status.handle
async def on_pool_status(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    pool_name = _extract_after_command(ctx, "卡池状态") or None
    stats = _pool_stats(int(ctx.group_id), pool_name)
    if not stats:
        await ctx.reply("当前没有卡池数据")
        return
    first_pool = _get_first_day_pool(int(ctx.group_id))
    streak_rules = _list_streak_rules(int(ctx.group_id))
    invite_rules = _list_invite_rules(int(ctx.group_id))
    lines = ["卡池状态"]
    for row in stats:
        if int(row.get('has_reusable') or 0) == 1:
            lines.append(f"- {row['pool_name']}：包含公共卡密，可重复发放，已发 {row['used']}")
        else:
            lines.append(f"- {row['pool_name']}：总数 {row['total']}，剩余 {row['available']}，已发 {row['used']}")
    lines.append(f"首日签到奖励：{first_pool or '未设置'}")
    if streak_rules:
        lines.append("连续签到奖励：" + "；".join(f"{days}天→{pool}" for days, pool in streak_rules))
    else:
        lines.append("连续签到奖励：未设置")
    if invite_rules:
        lines.append("邀请奖励：" + "；".join(f"{count}人→{pool}" for count, pool in invite_rules))
    else:
        lines.append("邀请奖励：未设置")
    await ctx.reply("\n".join(lines))


invite_stats = CommandPlugin(
    name="invite_stats",
    command="邀请统计",
    description="show invite stats",
    meta=PluginMeta(name="invite_stats", version="1.0.0", author="OpenClaw", description="邀请统计"),
)


@invite_stats.handle
async def on_invite_stats(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("请在群里使用这个命令")
        return
    target = _extract_target_user_id(ctx) or ctx.user_id
    if target is None:
        await ctx.reply("无法识别用户")
        return
    count = _get_invite_count(int(ctx.group_id), int(target))
    await ctx.reply(f"用户 {target} 当前有效邀请人数：{count}")

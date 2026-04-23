from __future__ import annotations

from datetime import datetime
import re
import time

from app.auth import is_owner
from app.core.plugin import CommandPlugin, PluginMeta
from app.db import _ensure_column, get_conn

plugin = None


def _ensure_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_admin_settings (
                group_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                auto_ban INTEGER NOT NULL DEFAULT 1,
                warn_threshold INTEGER NOT NULL DEFAULT 3,
                auto_ban_duration INTEGER NOT NULL DEFAULT 600,
                auto_recall_enabled INTEGER NOT NULL DEFAULT 0,
                auto_recall_seconds INTEGER NOT NULL DEFAULT 0,
                welcome_enabled INTEGER NOT NULL DEFAULT 0,
                welcome_template TEXT NOT NULL DEFAULT '欢迎入群，@用户',
                leave_notice_enabled INTEGER NOT NULL DEFAULT 0,
                recall_notice_enabled INTEGER NOT NULL DEFAULT 0,
                link_check_enabled INTEGER NOT NULL DEFAULT 0,
                spam_check_enabled INTEGER NOT NULL DEFAULT 0,
                spam_threshold INTEGER NOT NULL DEFAULT 5,
                spam_window_seconds INTEGER NOT NULL DEFAULT 20,
                global_word_mode INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_admin_words (
                group_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                PRIMARY KEY (group_id, word)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_admin_whitelist (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (group_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_admin_warns (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                warn_count INTEGER NOT NULL DEFAULT 0,
                last_reason TEXT DEFAULT '',
                last_at TEXT DEFAULT '',
                PRIMARY KEY (group_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                actor_user_id INTEGER NOT NULL DEFAULT 0,
                target_user_id INTEGER NOT NULL DEFAULT 0,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_admin_spam_records (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                hit_time INTEGER NOT NULL,
                content TEXT NOT NULL DEFAULT ''
            )
            """
        )
        _ensure_column(conn, "group_admin_settings", "auto_recall_enabled", "auto_recall_enabled INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "group_admin_settings", "auto_recall_seconds", "auto_recall_seconds INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "group_admin_settings", "welcome_enabled", "welcome_enabled INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "group_admin_settings", "welcome_template", "welcome_template TEXT NOT NULL DEFAULT '欢迎入群，@用户'")
        _ensure_column(conn, "group_admin_settings", "leave_notice_enabled", "leave_notice_enabled INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "group_admin_settings", "recall_notice_enabled", "recall_notice_enabled INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "group_admin_settings", "link_check_enabled", "link_check_enabled INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "group_admin_settings", "spam_check_enabled", "spam_check_enabled INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "group_admin_settings", "spam_threshold", "spam_threshold INTEGER NOT NULL DEFAULT 5")
        _ensure_column(conn, "group_admin_settings", "spam_window_seconds", "spam_window_seconds INTEGER NOT NULL DEFAULT 20")
        _ensure_column(conn, "group_admin_settings", "global_word_mode", "global_word_mode INTEGER NOT NULL DEFAULT 0")


_ensure_tables()


def _is_group_admin(ctx) -> bool:
    return ctx.role in {"admin", "owner"} or is_owner(ctx.user_id)


def _ensure_group(ctx) -> bool:
    return ctx.is_group


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


def _parse_duration_seconds(raw: str) -> int | None:
    raw = raw.strip().lower()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw) * 60
    units = {"m": 60, "h": 3600, "d": 86400}
    unit = raw[-1]
    num = raw[:-1]
    if unit in units and num.isdigit():
        return int(num) * units[unit]
    return None


def _get_settings(group_id: int) -> dict:
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO group_admin_settings (group_id) VALUES (?)", (group_id,))
        row = conn.execute(
            "SELECT enabled, auto_ban, warn_threshold, auto_ban_duration, auto_recall_enabled, auto_recall_seconds, "
            "welcome_enabled, welcome_template, leave_notice_enabled, recall_notice_enabled, link_check_enabled, spam_check_enabled, spam_threshold, spam_window_seconds, global_word_mode "
            "FROM group_admin_settings WHERE group_id=?",
            (group_id,),
        ).fetchone()
        if row is None:
            return {
                "enabled": 1,
                "auto_ban": 1,
                "warn_threshold": 3,
                "auto_ban_duration": 600,
                "auto_recall_enabled": 0,
                "auto_recall_seconds": 0,
                "welcome_enabled": 0,
                "welcome_template": "欢迎入群，@用户",
                "leave_notice_enabled": 0,
                "recall_notice_enabled": 0,
                "link_check_enabled": 0,
                "spam_check_enabled": 0,
                "spam_threshold": 5,
                "spam_window_seconds": 20,
                "global_word_mode": 0,
            }
        return dict(row)


def _update_setting(group_id: int, field: str, value) -> None:
    _get_settings(group_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE group_admin_settings SET {field}=? WHERE group_id=?", (value, group_id))


def _log_action(group_id: int, action: str, detail: str = '', actor_user_id: int | None = None, target_user_id: int | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO group_admin_logs (group_id, actor_user_id, target_user_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (group_id, int(actor_user_id or 0), int(target_user_id or 0), action, detail, datetime.utcnow().isoformat(timespec="seconds")),
        )


def _list_logs(group_id: int, limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT actor_user_id, target_user_id, action, detail, created_at FROM group_admin_logs WHERE group_id=? ORDER BY id DESC LIMIT ?",
            (group_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def _render_welcome(template: str, user_id: int) -> str:
    text = (template or '欢迎入群，@用户').replace('@用户', f'@{user_id}').replace('{user_id}', str(user_id))
    return text


def _append_spam_record(group_id: int, user_id: int, content: str) -> int:
    now_ts = int(time.time())
    settings = _get_settings(group_id)
    window_seconds = max(5, int(settings.get('spam_window_seconds') or 20))
    cutoff = now_ts - window_seconds
    with get_conn() as conn:
        conn.execute("DELETE FROM group_admin_spam_records WHERE group_id=? AND user_id=? AND hit_time < ?", (group_id, user_id, cutoff))
        conn.execute(
            "INSERT INTO group_admin_spam_records (group_id, user_id, hit_time, content) VALUES (?, ?, ?, ?)",
            (group_id, user_id, now_ts, (content or '')[:200]),
        )
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM group_admin_spam_records WHERE group_id=? AND user_id=? AND hit_time >= ?",
            (group_id, user_id, cutoff),
        ).fetchone()
        return int(row['cnt'] or 0)


def _has_link_content(text: str) -> bool:
    value = (text or '').lower()
    return bool(re.search(r'https?://|www\.|t\.me/|discord\.gg/|qq群|加v|vx|wx|二维码', value))


def get_group_admin_notice_settings(group_id: int | None) -> dict:
    if not group_id:
        return {}
    return _get_settings(int(group_id))


def get_auto_recall_seconds(group_id: int | None) -> int:
    if not group_id:
        return 0
    settings = _get_settings(int(group_id))
    if int(settings.get("auto_recall_enabled") or 0) != 1:
        return 0
    seconds = int(settings.get("auto_recall_seconds") or 0)
    return max(0, seconds)


def _list_words(group_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT word FROM group_admin_words WHERE group_id=? ORDER BY word ASC", (group_id,)).fetchall()
        return [str(r["word"]) for r in rows]


def _add_word(group_id: int, word: str) -> None:
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO group_admin_words (group_id, word) VALUES (?, ?)", (group_id, word))


def _remove_word(group_id: int, word: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM group_admin_words WHERE group_id=? AND word=?", (group_id, word))


def _clear_words(group_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM group_admin_words WHERE group_id=?", (group_id,))


def _is_whitelisted(group_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM group_admin_whitelist WHERE group_id=? AND user_id=?",
            (group_id, user_id),
        ).fetchone()
        return row is not None


def _add_whitelist(group_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO group_admin_whitelist (group_id, user_id) VALUES (?, ?)",
            (group_id, user_id),
        )


def _remove_whitelist(group_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM group_admin_whitelist WHERE group_id=? AND user_id=?", (group_id, user_id))


def _list_whitelist(group_id: int) -> list[int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id FROM group_admin_whitelist WHERE group_id=? ORDER BY user_id ASC",
            (group_id,),
        ).fetchall()
        return [int(r["user_id"]) for r in rows]


def _get_warn_info(group_id: int, user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT warn_count, last_reason, last_at FROM group_admin_warns WHERE group_id=? AND user_id=?",
            (group_id, user_id),
        ).fetchone()
        if row is None:
            return {"warn_count": 0, "last_reason": "", "last_at": ""}
        return dict(row)


def _add_warn(group_id: int, user_id: int, reason: str) -> int:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT warn_count FROM group_admin_warns WHERE group_id=? AND user_id=?",
            (group_id, user_id),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO group_admin_warns (group_id, user_id, warn_count, last_reason, last_at) VALUES (?, ?, ?, ?, ?)",
                (group_id, user_id, 1, reason, now),
            )
            return 1
        count = int(row["warn_count"]) + 1
        conn.execute(
            "UPDATE group_admin_warns SET warn_count=?, last_reason=?, last_at=? WHERE group_id=? AND user_id=?",
            (count, reason, now, group_id, user_id),
        )
        return count


def _clear_warns(group_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM group_admin_warns WHERE group_id=? AND user_id=?", (group_id, user_id))


def _parse_target_and_tail(ctx, command: str) -> tuple[int | None, str]:
    target = _extract_target_user_id(ctx)
    rest = _extract_after_command(ctx, command)
    parts = rest.split(maxsplit=1)
    if not parts:
        return target, ""
    if parts[0].startswith("@") or parts[0].isdigit():
        return target, parts[1].strip() if len(parts) > 1 else ""
    return target, rest


group_admin_help = CommandPlugin(
    name="group_admin_help",
    command="群管帮助",
    description="show group admin help",
    meta=PluginMeta(name="group_admin_help", version="2.0.0", author="OpenClaw", description="group admin help"),
)


@group_admin_help.handle
async def on_group_admin_help(ctx):
    await ctx.reply(
        "群管命令 v2：\n"
        "群管帮助\n"
        "群管状态\n"
        "群管开 / 群管关\n"
        "开启自动撤回 秒数\n"
        "关闭自动撤回\n"
        "自动撤回状态\n"
        "撤回 [消息ID]\n"
        "禁言 @某人 10m/1h/1d\n"
        "解禁 @某人\n"
        "全员禁言 开 / 关\n"
        "踢人 @某人\n"
        "设管理 @某人 / 取消管理 @某人\n"
        "改群名 新名字\n"
        "改名片 @某人 新名片\n"
        "查成员 @某人\n"
        "成员列表 [数量]\n"
        "添加违禁词 词语\n"
        "删除违禁词 词语\n"
        "违禁词列表\n"
        "清空违禁词\n"
        "警告 @某人 原因\n"
        "警告记录 @某人\n"
        "清空警告 @某人\n"
        "自动禁言 开 / 关\n"
        "自动禁言时长 10m\n"
        "警告阈值 3\n"
        "白名单 @某人\n"
        "取消白名单 @某人\n"
        "白名单列表\n"
        "欢迎开 / 欢迎关\n"
        "设置欢迎词 内容（支持 @用户 占位）\n"
        "退群通知 开 / 关\n"
        "撤回通知 开 / 关\n"
        "链接审核 开 / 关\n"
        "刷屏检测 开 / 关\n"
        "刷屏阈值 次数\n"
        "刷屏窗口 秒数\n"
        "群管日志 [数量]"
    )


group_admin_status = CommandPlugin(
    name="group_admin_status",
    command="群管状态",
    description="show group admin status",
    meta=PluginMeta(name="group_admin_status", version="2.0.0", author="OpenClaw", description="show group admin status"),
)


@group_admin_status.handle
async def on_group_admin_status(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    settings = _get_settings(ctx.group_id)
    words = _list_words(ctx.group_id)
    white = _list_whitelist(ctx.group_id)
    await ctx.reply(
        f"群管状态\n"
        f"群管开关：{'开' if settings['enabled'] else '关'}\n"
        f"自动禁言：{'开' if settings['auto_ban'] else '关'}\n"
        f"警告阈值：{settings['warn_threshold']}\n"
        f"自动禁言时长：{settings['auto_ban_duration']} 秒\n"
        f"自动撤回：{'开' if int(settings.get('auto_recall_enabled') or 0) == 1 else '关'}\n"
        f"欢迎入群：{'开' if int(settings.get('welcome_enabled') or 0) == 1 else '关'}\n"
        f"退群通知：{'开' if int(settings.get('leave_notice_enabled') or 0) == 1 else '关'}\n"
        f"撤回通知：{'开' if int(settings.get('recall_notice_enabled') or 0) == 1 else '关'}\n"
        f"链接审核：{'开' if int(settings.get('link_check_enabled') or 0) == 1 else '关'}\n"
        f"刷屏检测：{'开' if int(settings.get('spam_check_enabled') or 0) == 1 else '关'}（{settings.get('spam_threshold')} 次/{settings.get('spam_window_seconds')} 秒）\n"
        f"违禁词数量：{len(words)}\n"
        f"白名单数量：{len(white)}"
    )


group_admin_toggle = CommandPlugin(
    name="group_admin_toggle",
    command="群管",
    description="toggle group admin system",
    meta=PluginMeta(name="group_admin_toggle", version="2.0.0", author="OpenClaw", description="toggle group admin system"),
)


@group_admin_toggle.handle
async def on_group_admin_toggle(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, "群管")
    if arg not in {"开", "关"}:
        await ctx.reply("用法：群管 开 / 群管 关")
        return
    _update_setting(ctx.group_id, "enabled", 1 if arg == "开" else 0)
    await ctx.reply("已开启群管系统" if arg == "开" else "已关闭群管系统")


auto_recall_status = CommandPlugin(
    name="auto_recall_status",
    command="自动撤回状态",
    description="show auto recall status",
    meta=PluginMeta(name="auto_recall_status", version="2.1.0", author="OpenClaw", description="自动撤回状态"),
)


@auto_recall_status.handle
async def on_auto_recall_status(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    settings = _get_settings(int(ctx.group_id))
    enabled = int(settings.get("auto_recall_enabled") or 0) == 1
    seconds = int(settings.get("auto_recall_seconds") or 0)
    if enabled and seconds > 0:
        await ctx.reply(f"当前本群自动撤回：已开启\n撤回时间：{seconds} 秒")
    else:
        await ctx.reply("当前本群自动撤回：已关闭")


enable_auto_recall = CommandPlugin(
    name="enable_auto_recall",
    command="开启自动撤回",
    description="enable auto recall for this group",
    meta=PluginMeta(name="enable_auto_recall", version="2.1.0", author="OpenClaw", description="开启自动撤回"),
)

start_auto_recall = CommandPlugin(
    name="start_auto_recall",
    command="开始自动撤回",
    description="alias for enable auto recall",
    meta=PluginMeta(name="start_auto_recall", version="2.1.0", author="OpenClaw", description="开始自动撤回"),
)


async def _handle_enable_auto_recall(ctx, command_text: str) -> None:
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, command_text).strip()
    if not arg.isdigit():
        await ctx.reply("用法：开启自动撤回 秒数\n或：开始自动撤回 秒数")
        return
    seconds = int(arg)
    if seconds <= 0:
        await ctx.reply("秒数必须大于 0")
        return
    _update_setting(int(ctx.group_id), "auto_recall_enabled", 1)
    _update_setting(int(ctx.group_id), "auto_recall_seconds", seconds)
    await ctx.reply(f"已开启本群自动撤回\n撤回时间：{seconds} 秒")


@enable_auto_recall.handle
async def on_enable_auto_recall(ctx):
    await _handle_enable_auto_recall(ctx, "开启自动撤回")


@start_auto_recall.handle
async def on_start_auto_recall(ctx):
    await _handle_enable_auto_recall(ctx, "开始自动撤回")


disable_auto_recall = CommandPlugin(
    name="disable_auto_recall",
    command="关闭自动撤回",
    description="disable auto recall for this group",
    meta=PluginMeta(name="disable_auto_recall", version="2.1.0", author="OpenClaw", description="关闭自动撤回"),
)

stop_auto_recall = CommandPlugin(
    name="stop_auto_recall",
    command="停止自动撤回",
    description="alias for disable auto recall",
    meta=PluginMeta(name="stop_auto_recall", version="2.1.0", author="OpenClaw", description="停止自动撤回"),
)


async def _handle_disable_auto_recall(ctx) -> None:
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    _update_setting(int(ctx.group_id), "auto_recall_enabled", 0)
    _update_setting(int(ctx.group_id), "auto_recall_seconds", 0)
    await ctx.reply("已关闭本群自动撤回")


@disable_auto_recall.handle
async def on_disable_auto_recall(ctx):
    await _handle_disable_auto_recall(ctx)


@stop_auto_recall.handle
async def on_stop_auto_recall(ctx):
    await _handle_disable_auto_recall(ctx)


recall_msg = CommandPlugin(
    name="recall_msg",
    command="撤回",
    description="recall message",
    meta=PluginMeta(name="recall_msg", version="2.0.0", author="OpenClaw", description="recall message"),
)


@recall_msg.handle
async def on_recall_msg(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, "撤回")
    message_id = arg if arg else ctx.message_id
    if not message_id:
        await ctx.reply("未找到可撤回的消息ID")
        return
    await ctx.api.delete_msg(message_id)


ban_user = CommandPlugin(
    name="ban_user",
    command="禁言",
    description="ban group member",
    meta=PluginMeta(name="ban_user", version="2.0.0", author="OpenClaw", description="ban group member"),
)


@ban_user.handle
async def on_ban_user(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：禁言 @某人 10m")
        return
    args = _extract_after_command(ctx, "禁言").split()
    duration = None
    for token in reversed(args):
        duration = _parse_duration_seconds(token)
        if duration is not None:
            break
    if duration is None:
        await ctx.reply("时长格式示例：10m / 1h / 1d / 30（默认按分钟）")
        return
    await ctx.api.set_group_ban(ctx.group_id, target, duration)
    await ctx.reply(f"已禁言 {target}，时长 {duration} 秒")


unban_user = CommandPlugin(
    name="unban_user",
    command="解禁",
    description="unban group member",
    meta=PluginMeta(name="unban_user", version="2.0.0", author="OpenClaw", description="unban group member"),
)


@unban_user.handle
async def on_unban_user(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：解禁 @某人")
        return
    await ctx.api.set_group_ban(ctx.group_id, target, 0)
    await ctx.reply(f"已解除禁言：{target}")


whole_ban = CommandPlugin(
    name="whole_ban",
    command="全员禁言",
    description="toggle whole group ban",
    meta=PluginMeta(name="whole_ban", version="2.0.0", author="OpenClaw", description="toggle whole group ban"),
)


@whole_ban.handle
async def on_whole_ban(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, "全员禁言")
    if arg not in {"开", "关"}:
        await ctx.reply("用法：全员禁言 开 / 全员禁言 关")
        return
    enable = arg == "开"
    await ctx.api.set_group_whole_ban(ctx.group_id, enable)
    await ctx.reply("已开启全员禁言" if enable else "已关闭全员禁言")


kick_user = CommandPlugin(
    name="kick_user",
    command="踢人",
    description="kick group member",
    meta=PluginMeta(name="kick_user", version="2.0.0", author="OpenClaw", description="kick group member"),
)


@kick_user.handle
async def on_kick_user(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：踢人 @某人")
        return
    await ctx.api.set_group_kick(ctx.group_id, target)
    await ctx.reply(f"已踢出成员：{target}")


set_admin = CommandPlugin(
    name="set_admin",
    command="设管理",
    description="set group admin",
    meta=PluginMeta(name="set_admin", version="2.0.0", author="OpenClaw", description="set group admin"),
)


@set_admin.handle
async def on_set_admin(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：设管理 @某人")
        return
    await ctx.api.set_group_admin(ctx.group_id, target, True)
    await ctx.reply(f"已设为管理：{target}")


unset_admin = CommandPlugin(
    name="unset_admin",
    command="取消管理",
    description="unset group admin",
    meta=PluginMeta(name="unset_admin", version="2.0.0", author="OpenClaw", description="unset group admin"),
)


@unset_admin.handle
async def on_unset_admin(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：取消管理 @某人")
        return
    await ctx.api.set_group_admin(ctx.group_id, target, False)
    await ctx.reply(f"已取消管理：{target}")


set_group_name = CommandPlugin(
    name="set_group_name",
    command="改群名",
    description="set group name",
    meta=PluginMeta(name="set_group_name", version="2.0.0", author="OpenClaw", description="set group name"),
)


@set_group_name.handle
async def on_set_group_name(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    name = _extract_after_command(ctx, "改群名")
    if not name:
        await ctx.reply("用法：改群名 新名字")
        return
    await ctx.api.set_group_name(ctx.group_id, name)
    await ctx.reply(f"已修改群名：{name}")


set_group_card = CommandPlugin(
    name="set_group_card",
    command="改名片",
    description="set group card",
    meta=PluginMeta(name="set_group_card", version="2.0.0", author="OpenClaw", description="set group card"),
)


@set_group_card.handle
async def on_set_group_card(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target, tail = _parse_target_and_tail(ctx, "改名片")
    if not target or not tail:
        await ctx.reply("用法：改名片 @某人 新名片")
        return
    await ctx.api.set_group_card(ctx.group_id, target, tail)
    await ctx.reply(f"已修改 {target} 的群名片")


member_info = CommandPlugin(
    name="member_info",
    command="查成员",
    description="get member info",
    meta=PluginMeta(name="member_info", version="2.0.0", author="OpenClaw", description="get member info"),
)


@member_info.handle
async def on_member_info(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：查成员 @某人")
        return
    data = await ctx.api.get_group_member_info(ctx.group_id, target)
    member = data.get("data") or {}
    if not member:
        await ctx.reply("未查询到成员信息")
        return
    nickname = member.get("nickname", "-")
    card = member.get("card", "-")
    role = member.get("role", "-")
    title = member.get("title", "-")
    level = member.get("level", "-")
    await ctx.reply(
        f"成员信息\nQQ：{target}\n昵称：{nickname}\n群名片：{card}\n角色：{role}\n头衔：{title}\n等级：{level}"
    )


member_list = CommandPlugin(
    name="member_list",
    command="成员列表",
    description="list group members",
    meta=PluginMeta(name="member_list", version="2.0.0", author="OpenClaw", description="list group members"),
)


@member_list.handle
async def on_member_list(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    raw = _extract_after_command(ctx, "成员列表")
    limit = 10
    if raw.isdigit():
        limit = max(1, min(50, int(raw)))
    data = await ctx.api.get_group_member_list(ctx.group_id)
    items = data.get("data") or []
    if not items:
        await ctx.reply("成员列表为空")
        return
    lines = []
    for item in items[:limit]:
        uid = item.get("user_id", "-")
        nickname = item.get("nickname") or "-"
        card = item.get("card") or "-"
        role = item.get("role") or "member"
        lines.append(f"{uid} | {nickname} | 名片:{card} | 角色:{role}")
    await ctx.reply("群成员列表：\n" + "\n".join(lines))


add_bad_word = CommandPlugin(
    name="add_bad_word",
    command="添加违禁词",
    description="add bad word",
    meta=PluginMeta(name="add_bad_word", version="2.0.0", author="OpenClaw", description="add bad word"),
)


@add_bad_word.handle
async def on_add_bad_word(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    word = _extract_after_command(ctx, "添加违禁词")
    if not word:
        await ctx.reply("用法：添加违禁词 词语")
        return
    _add_word(ctx.group_id, word)
    await ctx.reply(f"已添加违禁词：{word}")


del_bad_word = CommandPlugin(
    name="del_bad_word",
    command="删除违禁词",
    description="delete bad word",
    meta=PluginMeta(name="del_bad_word", version="2.0.0", author="OpenClaw", description="delete bad word"),
)


@del_bad_word.handle
async def on_del_bad_word(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    word = _extract_after_command(ctx, "删除违禁词")
    if not word:
        await ctx.reply("用法：删除违禁词 词语")
        return
    _remove_word(ctx.group_id, word)
    await ctx.reply(f"已删除违禁词：{word}")


list_bad_words = CommandPlugin(
    name="list_bad_words",
    command="违禁词列表",
    description="list bad words",
    meta=PluginMeta(name="list_bad_words", version="2.0.0", author="OpenClaw", description="list bad words"),
)


@list_bad_words.handle
async def on_list_bad_words(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    words = _list_words(ctx.group_id)
    if not words:
        await ctx.reply("当前没有违禁词")
        return
    await ctx.reply("违禁词列表：\n" + "\n".join(words))


clear_bad_words = CommandPlugin(
    name="clear_bad_words",
    command="清空违禁词",
    description="clear bad words",
    meta=PluginMeta(name="clear_bad_words", version="2.0.0", author="OpenClaw", description="clear bad words"),
)


@clear_bad_words.handle
async def on_clear_bad_words(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    _clear_words(ctx.group_id)
    await ctx.reply("已清空违禁词")


warn_user = CommandPlugin(
    name="warn_user",
    command="警告",
    description="warn user",
    meta=PluginMeta(name="warn_user", version="2.0.0", author="OpenClaw", description="warn user"),
)


@warn_user.handle
async def on_warn_user(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target, reason = _parse_target_and_tail(ctx, "警告")
    if not target:
        await ctx.reply("用法：警告 @某人 原因")
        return
    reason = reason or "管理员警告"
    count = _add_warn(ctx.group_id, target, reason)
    settings = _get_settings(ctx.group_id)
    reply = f"已警告 {target}，当前警告次数：{count}，原因：{reason}"
    if settings["auto_ban"] and count >= int(settings["warn_threshold"]):
        duration = int(settings["auto_ban_duration"])
        await ctx.api.set_group_ban(ctx.group_id, target, duration)
        reply += f"\n已达到阈值，自动禁言 {duration} 秒"
    await ctx.reply(reply)


warn_info = CommandPlugin(
    name="warn_info",
    command="警告记录",
    description="warn info",
    meta=PluginMeta(name="warn_info", version="2.0.0", author="OpenClaw", description="warn info"),
)


@warn_info.handle
async def on_warn_info(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：警告记录 @某人")
        return
    info = _get_warn_info(ctx.group_id, target)
    await ctx.reply(
        f"警告记录\nQQ：{target}\n次数：{info['warn_count']}\n最近原因：{info['last_reason'] or '-'}\n最近时间：{info['last_at'] or '-'}"
    )


clear_warns = CommandPlugin(
    name="clear_warns",
    command="清空警告",
    description="clear warns",
    meta=PluginMeta(name="clear_warns", version="2.0.0", author="OpenClaw", description="clear warns"),
)


@clear_warns.handle
async def on_clear_warns(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：清空警告 @某人")
        return
    _clear_warns(ctx.group_id, target)
    await ctx.reply(f"已清空 {target} 的警告记录")


auto_ban_toggle = CommandPlugin(
    name="auto_ban_toggle",
    command="自动禁言",
    description="toggle auto ban",
    meta=PluginMeta(name="auto_ban_toggle", version="2.0.0", author="OpenClaw", description="toggle auto ban"),
)


@auto_ban_toggle.handle
async def on_auto_ban_toggle(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, "自动禁言")
    if arg not in {"开", "关"}:
        await ctx.reply("用法：自动禁言 开 / 自动禁言 关")
        return
    _update_setting(ctx.group_id, "auto_ban", 1 if arg == "开" else 0)
    await ctx.reply("已开启自动禁言" if arg == "开" else "已关闭自动禁言")


auto_ban_duration = CommandPlugin(
    name="auto_ban_duration",
    command="自动禁言时长",
    description="set auto ban duration",
    meta=PluginMeta(name="auto_ban_duration", version="2.0.0", author="OpenClaw", description="set auto ban duration"),
)


@auto_ban_duration.handle
async def on_auto_ban_duration(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    raw = _extract_after_command(ctx, "自动禁言时长")
    seconds = _parse_duration_seconds(raw)
    if seconds is None:
        await ctx.reply("用法：自动禁言时长 10m / 1h / 1d")
        return
    _update_setting(ctx.group_id, "auto_ban_duration", seconds)
    await ctx.reply(f"已设置自动禁言时长：{seconds} 秒")


warn_threshold = CommandPlugin(
    name="warn_threshold",
    command="警告阈值",
    description="set warn threshold",
    meta=PluginMeta(name="warn_threshold", version="2.0.0", author="OpenClaw", description="set warn threshold"),
)


@warn_threshold.handle
async def on_warn_threshold(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    raw = _extract_after_command(ctx, "警告阈值")
    if not raw.isdigit():
        await ctx.reply("用法：警告阈值 3")
        return
    value = max(1, min(20, int(raw)))
    _update_setting(ctx.group_id, "warn_threshold", value)
    await ctx.reply(f"已设置警告阈值：{value}")


add_white = CommandPlugin(
    name="add_white",
    command="白名单",
    description="add whitelist user",
    meta=PluginMeta(name="add_white", version="2.0.0", author="OpenClaw", description="add whitelist user"),
)


@add_white.handle
async def on_add_white(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：白名单 @某人")
        return
    _add_whitelist(ctx.group_id, target)
    await ctx.reply(f"已加入白名单：{target}")


remove_white = CommandPlugin(
    name="remove_white",
    command="取消白名单",
    description="remove whitelist user",
    meta=PluginMeta(name="remove_white", version="2.0.0", author="OpenClaw", description="remove whitelist user"),
)


@remove_white.handle
async def on_remove_white(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    if not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    target = _extract_target_user_id(ctx)
    if not target:
        await ctx.reply("用法：取消白名单 @某人")
        return
    _remove_whitelist(ctx.group_id, target)
    await ctx.reply(f"已移出白名单：{target}")


list_white = CommandPlugin(
    name="list_white",
    command="白名单列表",
    description="list whitelist users",
    meta=PluginMeta(name="list_white", version="2.0.0", author="OpenClaw", description="list whitelist users"),
)


@list_white.handle
async def on_list_white(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    users = _list_whitelist(ctx.group_id)
    if not users:
        await ctx.reply("白名单为空")
        return
    await ctx.reply("白名单列表：\n" + "\n".join(str(x) for x in users))


welcome_toggle = CommandPlugin(name="welcome_toggle", command="欢迎", description="toggle welcome", meta=PluginMeta(name="welcome_toggle", version="3.0.0", author="OpenClaw", description="toggle welcome"))
set_welcome_text = CommandPlugin(name="set_welcome_text", command="设置欢迎词", description="set welcome template", meta=PluginMeta(name="set_welcome_text", version="3.0.0", author="OpenClaw", description="set welcome template"))
leave_notice_toggle = CommandPlugin(name="leave_notice_toggle", command="退群通知", description="toggle leave notice", meta=PluginMeta(name="leave_notice_toggle", version="3.0.0", author="OpenClaw", description="toggle leave notice"))
recall_notice_toggle = CommandPlugin(name="recall_notice_toggle", command="撤回通知", description="toggle recall notice", meta=PluginMeta(name="recall_notice_toggle", version="3.0.0", author="OpenClaw", description="toggle recall notice"))
link_check_toggle = CommandPlugin(name="link_check_toggle", command="链接审核", description="toggle link check", meta=PluginMeta(name="link_check_toggle", version="3.0.0", author="OpenClaw", description="toggle link check"))
spam_check_toggle = CommandPlugin(name="spam_check_toggle", command="刷屏检测", description="toggle spam check", meta=PluginMeta(name="spam_check_toggle", version="3.0.0", author="OpenClaw", description="toggle spam check"))
spam_threshold_cmd = CommandPlugin(name="spam_threshold_cmd", command="刷屏阈值", description="set spam threshold", meta=PluginMeta(name="spam_threshold_cmd", version="3.0.0", author="OpenClaw", description="set spam threshold"))
spam_window_cmd = CommandPlugin(name="spam_window_cmd", command="刷屏窗口", description="set spam window", meta=PluginMeta(name="spam_window_cmd", version="3.0.0", author="OpenClaw", description="set spam window"))
admin_logs = CommandPlugin(name="admin_logs", command="群管日志", description="show admin logs", meta=PluginMeta(name="admin_logs", version="3.0.0", author="OpenClaw", description="show admin logs"))


@welcome_toggle.handle
async def on_welcome_toggle(ctx):
    if not _ensure_group(ctx) or not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, "欢迎")
    if arg not in {"开", "关"}:
        await ctx.reply("用法：欢迎 开 / 欢迎 关")
        return
    _update_setting(ctx.group_id, "welcome_enabled", 1 if arg == "开" else 0)
    _log_action(ctx.group_id, "welcome_toggle", arg, ctx.user_id)
    await ctx.reply("已开启入群欢迎" if arg == "开" else "已关闭入群欢迎")


@set_welcome_text.handle
async def on_set_welcome_text(ctx):
    if not _ensure_group(ctx) or not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    text = _extract_after_command(ctx, "设置欢迎词")
    if not text:
        await ctx.reply("用法：设置欢迎词 内容（支持 @用户 / {user_id}）")
        return
    _update_setting(ctx.group_id, "welcome_template", text)
    _log_action(ctx.group_id, "welcome_text", text, ctx.user_id)
    await ctx.reply("已设置欢迎词")


@leave_notice_toggle.handle
async def on_leave_notice_toggle(ctx):
    if not _ensure_group(ctx) or not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, "退群通知")
    if arg not in {"开", "关"}:
        await ctx.reply("用法：退群通知 开 / 关")
        return
    _update_setting(ctx.group_id, "leave_notice_enabled", 1 if arg == "开" else 0)
    await ctx.reply("已开启退群通知" if arg == "开" else "已关闭退群通知")


@recall_notice_toggle.handle
async def on_recall_notice_toggle(ctx):
    if not _ensure_group(ctx) or not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, "撤回通知")
    if arg not in {"开", "关"}:
        await ctx.reply("用法：撤回通知 开 / 关")
        return
    _update_setting(ctx.group_id, "recall_notice_enabled", 1 if arg == "开" else 0)
    await ctx.reply("已开启撤回通知" if arg == "开" else "已关闭撤回通知")


@link_check_toggle.handle
async def on_link_check_toggle(ctx):
    if not _ensure_group(ctx) or not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, "链接审核")
    if arg not in {"开", "关"}:
        await ctx.reply("用法：链接审核 开 / 关")
        return
    _update_setting(ctx.group_id, "link_check_enabled", 1 if arg == "开" else 0)
    await ctx.reply("已开启链接审核" if arg == "开" else "已关闭链接审核")


@spam_check_toggle.handle
async def on_spam_check_toggle(ctx):
    if not _ensure_group(ctx) or not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    arg = _extract_after_command(ctx, "刷屏检测")
    if arg not in {"开", "关"}:
        await ctx.reply("用法：刷屏检测 开 / 关")
        return
    _update_setting(ctx.group_id, "spam_check_enabled", 1 if arg == "开" else 0)
    await ctx.reply("已开启刷屏检测" if arg == "开" else "已关闭刷屏检测")


@spam_threshold_cmd.handle
async def on_spam_threshold_cmd(ctx):
    if not _ensure_group(ctx) or not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    raw = _extract_after_command(ctx, "刷屏阈值")
    if not raw.isdigit():
        await ctx.reply("用法：刷屏阈值 次数")
        return
    val = max(2, min(20, int(raw)))
    _update_setting(ctx.group_id, "spam_threshold", val)
    await ctx.reply(f"已设置刷屏阈值：{val}")


@spam_window_cmd.handle
async def on_spam_window_cmd(ctx):
    if not _ensure_group(ctx) or not _is_group_admin(ctx):
        await ctx.reply("你没有群管权限")
        return
    raw = _extract_after_command(ctx, "刷屏窗口")
    if not raw.isdigit():
        await ctx.reply("用法：刷屏窗口 秒数")
        return
    val = max(5, min(300, int(raw)))
    _update_setting(ctx.group_id, "spam_window_seconds", val)
    await ctx.reply(f"已设置刷屏窗口：{val} 秒")


@admin_logs.handle
async def on_admin_logs(ctx):
    if not _ensure_group(ctx):
        await ctx.reply("这个命令只能在群里用")
        return
    raw = _extract_after_command(ctx, "群管日志")
    limit = 10
    if raw.isdigit():
        limit = max(1, min(50, int(raw)))
    rows = _list_logs(ctx.group_id, limit)
    if not rows:
        await ctx.reply("当前没有群管日志")
        return
    lines = ["群管日志："]
    for r in rows:
        lines.append(f"- [{r['created_at']}] {r['action']} actor={r['actor_user_id']} target={r['target_user_id']} {r['detail']}")
    await ctx.reply("\n".join(lines))


class GroupAutoModerationPlugin:
    name = "group_auto_moderation"
    meta = PluginMeta(
        name="group_auto_moderation",
        version="3.0.0",
        author="OpenClaw",
        description="auto moderation for forbidden words, links, spam and warn-ban flow",
    )

    async def dispatch(self, ctx) -> bool:
        if not _ensure_group(ctx):
            return False
        if not ctx.text.strip():
            return False
        settings = _get_settings(ctx.group_id)
        if not int(settings.get("enabled", 1)):
            return False
        if _is_group_admin(ctx):
            return False
        if _is_whitelisted(ctx.group_id, ctx.user_id):
            return False
        if ctx.user_id is None:
            return False

        hit_reason = ""
        action_label = ""

        words = _list_words(ctx.group_id)
        hit = next((word for word in words if word and word in ctx.text), None)
        if hit:
            hit_reason = f"触发违禁词：{hit}"
            action_label = "bad_word"
        elif int(settings.get("link_check_enabled") or 0) == 1 and _has_link_content(ctx.text):
            hit_reason = "触发链接/引流内容"
            action_label = "link_check"
        elif int(settings.get("spam_check_enabled") or 0) == 1:
            count_in_window = _append_spam_record(ctx.group_id, ctx.user_id, ctx.text)
            if count_in_window >= int(settings.get("spam_threshold") or 5):
                hit_reason = f"触发刷屏检测：{count_in_window} 次/{int(settings.get('spam_window_seconds') or 20)} 秒"
                action_label = "spam_check"

        if not hit_reason:
            return False

        if ctx.message_id:
            try:
                await ctx.api.delete_msg(ctx.message_id)
            except Exception:
                pass

        count = _add_warn(ctx.group_id, ctx.user_id, hit_reason)
        _log_action(ctx.group_id, action_label, hit_reason, ctx.user_id, ctx.user_id)
        reply = f"已执行群管处理：{hit_reason}。用户 {ctx.user_id} 当前警告次数：{count}"

        if int(settings.get("auto_ban", 1)) and count >= int(settings.get("warn_threshold", 3)):
            duration = int(settings.get("auto_ban_duration", 600))
            try:
                await ctx.api.set_group_ban(ctx.group_id, ctx.user_id, duration)
                _log_action(ctx.group_id, "auto_ban", f"duration={duration}", 0, ctx.user_id)
                reply += f"，已自动禁言 {duration} 秒"
            except Exception:
                reply += "，自动禁言失败，请检查机器人权限"

        try:
            await ctx.reply(reply)
        except Exception:
            pass
        return False


class GroupNoticePlugin:
    name = "group_notice_events"
    meta = PluginMeta(
        name="group_notice_events",
        version="3.0.0",
        author="OpenClaw",
        description="welcome, leave and recall notice hooks",
    )

    async def dispatch(self, ctx) -> bool:
        event = ctx.raw_event or {}
        if event.get("post_type") != "notice":
            return False
        group_id = event.get("group_id")
        if not group_id:
            return False
        settings = _get_settings(int(group_id))
        notice_type = str(event.get("notice_type") or "")

        if notice_type == "group_increase" and int(settings.get("welcome_enabled") or 0) == 1:
            user_id = event.get("user_id")
            if user_id:
                msg = _render_welcome(str(settings.get("welcome_template") or ''), int(user_id))
                try:
                    await ctx.api.send_group_msg(int(group_id), msg)
                except Exception:
                    pass
                _log_action(int(group_id), "group_increase", msg, event.get("operator_id"), user_id)
                return False

        if notice_type == "group_decrease" and int(settings.get("leave_notice_enabled") or 0) == 1:
            user_id = event.get("user_id")
            operator_id = event.get("operator_id")
            sub_type = str(event.get("sub_type") or "")
            msg = f"成员离群通知\n用户：{user_id or '-'}\n操作者：{operator_id or '-'}\n类型：{sub_type or '-'}"
            try:
                await ctx.api.send_group_msg(int(group_id), msg)
            except Exception:
                pass
            _log_action(int(group_id), "group_decrease", msg, operator_id, user_id)
            return False

        if notice_type == "group_recall" and int(settings.get("recall_notice_enabled") or 0) == 1:
            user_id = event.get("user_id")
            operator_id = event.get("operator_id")
            message_id = event.get("message_id")
            msg = f"撤回提醒\n用户：{user_id or '-'}\n操作者：{operator_id or '-'}\n消息ID：{message_id or '-'}"
            try:
                await ctx.api.send_group_msg(int(group_id), msg)
            except Exception:
                pass
            _log_action(int(group_id), "group_recall", msg, operator_id, user_id)
            return False
        return False


group_auto_moderation = GroupAutoModerationPlugin()
group_notice_events = GroupNoticePlugin()
plugins = [
    group_admin_help,
    group_admin_status,
    group_admin_toggle,
    auto_recall_status,
    enable_auto_recall,
    start_auto_recall,
    disable_auto_recall,
    stop_auto_recall,
    recall_msg,
    ban_user,
    unban_user,
    whole_ban,
    kick_user,
    set_admin,
    unset_admin,
    set_group_name,
    set_group_card,
    member_info,
    member_list,
    add_bad_word,
    del_bad_word,
    list_bad_words,
    clear_bad_words,
    warn_user,
    warn_info,
    clear_warns,
    auto_ban_toggle,
    auto_ban_duration,
    warn_threshold,
    add_white,
    remove_white,
    list_white,
    welcome_toggle,
    set_welcome_text,
    leave_notice_toggle,
    recall_notice_toggle,
    link_check_toggle,
    spam_check_toggle,
    spam_threshold_cmd,
    spam_window_cmd,
    admin_logs,
    group_auto_moderation,
    group_notice_events,
]

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.auth import is_owner
from app.core.plugin import CommandPlugin, PluginMeta

BASE_DIR = Path(__file__).resolve().parent.parent
GIT_DIR = BASE_DIR / ".git"
BUILD_INFO_FILE = BASE_DIR / "BUILD_INFO.json"
VERSION_FILE = BASE_DIR / "VERSION"
DEFAULT_REPO = os.getenv("QQBOT_UPDATE_REPO", "3026591236/qqbot-framework")
DEFAULT_BRANCH = os.getenv("QQBOT_UPDATE_BRANCH", "main")
DEFAULT_TIMEOUT = float(os.getenv("QQBOT_UPDATE_TIMEOUT", "15"))
AUTO_NOTIFY_ENABLED = os.getenv("QQBOT_UPDATE_AUTO_NOTIFY", "true").lower() == "true"
AUTO_NOTIFY_INTERVAL = int(os.getenv("QQBOT_UPDATE_CHECK_INTERVAL", "1800"))
STATE_FILE = BASE_DIR / "data" / "update_checker_state.json"
RESULT_FILE = BASE_DIR / "data" / "update_checker_result.json"
UPDATE_SCRIPT = BASE_DIR / "deploy" / "auto-update.sh"
logger = logging.getLogger(__name__)

CATEGORY_RULES = [
    ("安装部署", ["deploy", "install", "bootstrap", "docker", "systemd", "napcat", "部署", "安装"]),
    ("更新系统", ["update", "updater", "更新"]),
    ("AI 功能", ["ai", "model", "relay", "中转", "模型"]),
    ("菜单与帮助", ["menu", "help", "菜单", "帮助"]),
    ("插件系统", ["plugin", "插件"]),
    ("群管功能", ["group", "admin", "moderation", "群管", "禁言", "违禁词"]),
    ("签到积分", ["checkin", "points", "签到", "积分", "补签"]),
    ("卡片消息", ["card", "json", "xml", "伪卡片", "卡片"]),
    ("命令路由", ["command", "router", "dispatch", "unknown", "命令", "路由"]),
    ("文档说明", ["readme", "docs", "release notes", "文档", "说明"]),
    ("稳定性修复", ["fix", "bug", "error", "crash", "稳定", "修复"]),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git 执行失败")
    return result.stdout.strip()


def _local_git_available() -> bool:
    return GIT_DIR.exists()


def _load_build_info() -> dict:
    if not BUILD_INFO_FILE.exists():
        return {}
    try:
        return json.loads(BUILD_INFO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_local_version() -> str:
    if VERSION_FILE.exists():
        try:
            return VERSION_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    build_info = _load_build_info()
    return (build_info.get("version") or "").strip()


def _deployment_mode() -> str:
    if _local_git_available():
        return "git"
    if BUILD_INFO_FILE.exists():
        return "build_info"
    return "unknown"


async def _github_get(url: str, *, raw: bool = False) -> str | dict:
    headers = {"User-Agent": "qqbot-framework/update-checker"}
    headers["Accept"] = "application/vnd.github.raw" if raw else "application/vnd.github+json"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text if raw else resp.json()


async def _fetch_remote_commit() -> tuple[str, str]:
    data = await _github_get(f"https://api.github.com/repos/{DEFAULT_REPO}/commits/{DEFAULT_BRANCH}")
    assert isinstance(data, dict)
    sha = (data.get("sha") or "").strip()
    message = ((data.get("commit") or {}).get("message") or "").strip()
    if not sha:
        raise RuntimeError("未获取到远端提交信息")
    return sha, message


async def _fetch_remote_version() -> str:
    try:
        text = await _github_get(
            f"https://raw.githubusercontent.com/{DEFAULT_REPO}/{DEFAULT_BRANCH}/VERSION",
            raw=True,
        )
        assert isinstance(text, str)
        return text.strip()
    except Exception:
        return ""


async def _fetch_compare_commits(local_sha: str, remote_sha: str) -> list[dict]:
    if not local_sha or not remote_sha or local_sha == remote_sha:
        return []
    try:
        data = await _github_get(
            f"https://api.github.com/repos/{DEFAULT_REPO}/compare/{local_sha}...{remote_sha}"
        )
        assert isinstance(data, dict)
        commits = data.get("commits") or []
        result = []
        for item in commits:
            sha = (item.get("sha") or "").strip()
            msg = ((item.get("commit") or {}).get("message") or "").strip()
            if sha and msg:
                result.append({"sha": sha, "message": msg})
        return result
    except Exception:
        logger.exception("failed to fetch compare commits: local=%s remote=%s", local_sha, remote_sha)
        return []


def _short_sha(value: str) -> str:
    return value[:7] if value else "-"


def _format_version_label(version: str, sha: str) -> str:
    version = (version or "").strip()
    if version:
        return f"{version}（{_short_sha(sha)}）"
    return _short_sha(sha)


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_result() -> dict:
    if not RESULT_FILE.exists():
        return {}
    try:
        return json.loads(RESULT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_result(data: dict) -> None:
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_commit_line(message: str) -> str:
    first = (message or "").splitlines()[0].strip()
    first = re.sub(r"\s+", " ", first)
    return first[:80] if len(first) > 80 else first


def _humanize_commit_line(message: str) -> str:
    line = _normalize_commit_line(message)
    lower = line.lower()

    replacements = [
        (r"\bversion\b", "版本号"),
        (r"\bupdate checks?\b", "更新检测"),
        (r"\bgit bootstrap deploy\b", "Git 一键部署"),
        (r"\bbootstrap\b", "一键部署"),
        (r"\bauto update\b", "自动更新"),
        (r"\bupdate checker\b", "更新检测器"),
        (r"\bmenu system\b", "菜单系统"),
        (r"\bplugin list\b", "插件列表"),
        (r"\bplugin\b", "插件"),
        (r"\bhelp\b", "帮助"),
        (r"\bnapcat\b", "NapCat"),
        (r"\binstaller\b", "安装器"),
        (r"\bpip\b", "pip"),
        (r"\bvenv\b", "venv"),
        (r"\bpython\b", "Python"),
        (r"\breadme\b", "README"),
        (r"\bbuild_info\b", "构建信息"),
        (r"\bbuild info\b", "构建信息"),
    ]

    def replace_terms(text: str) -> str:
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        return text

    if lower.startswith("add "):
        body = replace_terms(line[4:].strip())
        return f"新增：{body}"
    if lower.startswith("fix "):
        body = replace_terms(line[4:].strip())
        return f"修复：{body}"
    if lower.startswith("improve "):
        body = replace_terms(line[8:].strip())
        return f"优化：{body}"
    if lower.startswith("enhance "):
        body = replace_terms(line[8:].strip())
        return f"增强：{body}"
    if lower.startswith("show "):
        body = replace_terms(line[5:].strip())
        return f"显示优化：{body}"
    if lower.startswith("support "):
        body = replace_terms(line[8:].strip())
        return f"支持：{body}"
    if lower.startswith("auto-repair "):
        body = replace_terms(line[len("auto-repair "):].strip())
        return f"自动修复：{body}"
    if lower.startswith("require "):
        body = replace_terms(line[8:].strip())
        return f"要求：{body}"
    if lower.startswith("restrict "):
        body = replace_terms(line[9:].strip())
        return f"限制：{body}"
    if lower.startswith("humanize "):
        body = replace_terms(line[9:].strip())
        return f"中文化优化：{body}"

    if "humanize" in lower and "update summary" in lower and "chinese" in lower:
        return "更新内容提示已改为中文人话摘要，尽量直接说明更新了哪些功能、插件或修复了哪些问题"
    if "version" in lower and "update" in lower and "check" in lower:
        return "更新检测现在会显示正式版本号，并附带短提交号"
    if "napcat" in lower and ("hint" in lower or "login" in lower):
        return "NapCat 启动后会立即显示登录/扫码提示"
    if "pip" in lower and "venv" in lower:
        return "安装器会自动修复 pip 和 venv 相关前置环境"
    if "plugin" in lower and "detail" in lower:
        return "新增插件详情查看能力"
    if "menu" in lower:
        return "菜单系统与帮助展示已优化"
    if "unknown" in lower and "command" in lower:
        return "修复未知命令提示误拦截问题"
    if "ai" in lower and "model" in lower:
        return "AI 插件增加模型列表或模型切换相关能力"

    line = replace_terms(line)
    return f"更新：{line}"


def _guess_category(message: str) -> str | None:
    msg = (message or "").lower()
    for category, keywords in CATEGORY_RULES:
        if any(keyword.lower() in msg for keyword in keywords):
            return category
    return None


def _build_update_summary(commits: list[dict], fallback_message: str) -> str:
    if not commits:
        line = _humanize_commit_line(fallback_message) if fallback_message else "有代码更新，但暂未拿到详细变更说明"
        return f"更新内容：{line}"

    raw_lines = [_normalize_commit_line(item.get("message") or "") for item in commits]
    raw_lines = [line for line in raw_lines if line]
    if not raw_lines:
        line = _humanize_commit_line(fallback_message) if fallback_message else "有代码更新，但暂未拿到详细变更说明"
        return f"更新内容：{line}"

    categories = [_guess_category(line) for line in raw_lines]
    counter = Counter([x for x in categories if x])
    if counter:
        top_categories = [name for name, _ in counter.most_common(3)]
        overview = "、".join(top_categories)
    else:
        overview = "功能优化与修复"

    detail_lines = []
    for line in raw_lines[:4]:
        detail_lines.append(f"- {_humanize_commit_line(line)}")

    extra = ""
    if len(raw_lines) > 4:
        extra = f"\n- 另外还有 {len(raw_lines) - 4} 条更新"

    return f"本次更新主要涉及：{overview}\n" + "\n".join(detail_lines) + extra


async def _get_update_summary(local_sha: str, remote_sha: str, remote_message: str) -> str:
    commits = await _fetch_compare_commits(local_sha, remote_sha)
    return _build_update_summary(commits, remote_message)


async def _check_version_pair() -> tuple[str, str, str, str]:
    mode = _deployment_mode()
    if mode == "git":
        local_sha = _run_git(["rev-parse", "HEAD"])
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        remote_sha, remote_message = await _fetch_remote_commit()
        return local_sha, branch, remote_sha, remote_message
    if mode == "build_info":
        build_info = _load_build_info()
        local_sha = (build_info.get("commit") or "").strip()
        branch = (build_info.get("branch") or DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
        remote_sha, remote_message = await _fetch_remote_commit()
        if not local_sha:
            raise RuntimeError("本地 BUILD_INFO.json 缺少 commit 信息")
        return local_sha, branch, remote_sha, remote_message
    raise RuntimeError("当前部署缺少 git 信息和 BUILD_INFO.json，无法比较更新")


async def _notify_owners(api, text: str) -> None:
    owner_ids = [x.strip() for x in os.getenv("QQBOT_OWNER_IDS", "").split(",") if x.strip()]
    for owner_id in owner_ids:
        try:
            await api.send_private_msg(int(owner_id), text)
        except Exception:
            logger.exception("failed to notify owner about update: owner_id=%s", owner_id)


def _set_pending_update(
    branch: str,
    local_sha: str,
    remote_sha: str,
    remote_message: str,
    update_summary: str,
    local_version: str,
    remote_version: str,
) -> None:
    state = _load_state()
    state["pending_update"] = {
        "branch": branch,
        "local_sha": local_sha,
        "remote_sha": remote_sha,
        "remote_message": remote_message,
        "update_summary": update_summary,
        "local_version": local_version,
        "remote_version": remote_version,
        "created_at": _utc_now(),
    }
    _save_state(state)


def _clear_pending_update() -> None:
    state = _load_state()
    state.pop("pending_update", None)
    _save_state(state)


def _get_pending_update() -> dict:
    return _load_state().get("pending_update") or {}


def _can_auto_update() -> bool:
    return _deployment_mode() == "git" and UPDATE_SCRIPT.exists()


def _start_background_update(branch: str, remote_sha: str) -> None:
    state = _load_state()
    state["update_in_progress"] = {
        "branch": branch,
        "target_sha": remote_sha,
        "started_at": _utc_now(),
    }
    _save_state(state)
    subprocess.Popen(
        ["sh", str(UPDATE_SCRIPT), branch, remote_sha],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


async def _deliver_post_update_result(api) -> None:
    result = _load_result()
    if not result or result.get("notified"):
        return

    if result.get("ok"):
        text = (
            "机器人自动更新已完成\n"
            f"分支：{result.get('branch') or '-'}\n"
            f"更新前：{_format_version_label(result.get('old_version') or '', result.get('old_sha') or '')}\n"
            f"更新后：{_format_version_label(result.get('new_version') or '', result.get('new_sha') or '')}\n"
            f"时间：{result.get('finished_at') or '-'}"
        )
    else:
        text = (
            "机器人自动更新失败\n"
            f"分支：{result.get('branch') or '-'}\n"
            f"错误：{result.get('error') or '未知错误'}\n"
            "可手动发送：检查更新"
        )

    await _notify_owners(api, text)
    result["notified"] = True
    _save_result(result)

    state = _load_state()
    state.pop("update_in_progress", None)
    state.pop("pending_update", None)
    _save_state(state)


async def auto_update_notifier(api) -> None:
    if not AUTO_NOTIFY_ENABLED:
        logger.info("auto update notifier disabled")
        return
    if _deployment_mode() == "unknown":
        logger.info("auto update notifier skipped: no git or BUILD_INFO.json")
        return

    await asyncio.sleep(10)
    await _deliver_post_update_result(api)
    while True:
        try:
            local_sha, branch, remote_sha, remote_message = await _check_version_pair()
            local_version = _load_local_version()
            remote_version = await _fetch_remote_version()
            state = _load_state()
            last_notified_remote = state.get("last_notified_remote", "")
            update_in_progress = state.get("update_in_progress") or {}
            if local_sha != remote_sha and remote_sha != last_notified_remote and not update_in_progress:
                update_summary = await _get_update_summary(local_sha, remote_sha, remote_message)
                _set_pending_update(
                    branch,
                    local_sha,
                    remote_sha,
                    remote_message,
                    update_summary,
                    local_version,
                    remote_version,
                )
                if _can_auto_update():
                    await _notify_owners(
                        api,
                        "检测到机器人有新版本可更新\n"
                        f"仓库：{DEFAULT_REPO}\n"
                        f"分支：{branch}\n"
                        f"当前：{_format_version_label(local_version, local_sha)}\n"
                        f"最新：{_format_version_label(remote_version, remote_sha)}\n"
                        f"{update_summary}\n"
                        "回复：确认更新  开始自动更新\n"
                        "回复：取消更新  取消本次更新"
                    )
                else:
                    await _notify_owners(
                        api,
                        "检测到机器人有新版本可更新\n"
                        f"仓库：{DEFAULT_REPO}\n"
                        f"分支：{branch}\n"
                        f"当前：{_format_version_label(local_version, local_sha)}\n"
                        f"最新：{_format_version_label(remote_version, remote_sha)}\n"
                        f"{update_summary}\n"
                        "当前部署支持更新检测，但不支持自动执行更新。\n"
                        "如需自动更新，请改用 Git 工作区部署。"
                    )
                state = _load_state()
                state["last_notified_remote"] = remote_sha
                state["last_seen_local"] = local_sha
                _save_state(state)
            elif local_sha == remote_sha:
                state["last_seen_local"] = local_sha
                if state.get("last_notified_remote") == remote_sha:
                    state["last_notified_remote"] = ""
                _save_state(state)
            await _deliver_post_update_result(api)
        except Exception:
            logger.exception("auto update notifier failed")
        await asyncio.sleep(max(300, AUTO_NOTIFY_INTERVAL))


update_status = CommandPlugin(
    name="update_status",
    command="更新状态",
    description="show bot update status",
    meta=PluginMeta(name="update_status", version="1.3.0", author="OpenClaw", description="检查机器人更新状态"),
)


@update_status.handle
async def on_update_status(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以查看更新状态")
        return
    try:
        local_sha, branch, remote_sha, remote_message = await _check_version_pair()
        local_version = _load_local_version()
        remote_version = await _fetch_remote_version()
    except Exception as exc:
        await ctx.reply(f"检查更新失败：{exc}")
        return

    mode = _deployment_mode()
    mode_text = "git 工作区" if mode == "git" else "非 git 部署"
    if local_sha == remote_sha:
        await ctx.reply(
            "机器人已经是最新版本\n"
            f"部署方式：{mode_text}\n"
            f"分支：{branch}\n"
            f"本地：{_format_version_label(local_version, local_sha)}\n"
            f"远端：{_format_version_label(remote_version, remote_sha)}"
        )
        return

    pending = _get_pending_update()
    update_summary = pending.get("update_summary") if pending else await _get_update_summary(local_sha, remote_sha, remote_message)
    extra = "\n状态：等待确认更新" if pending else ""
    await ctx.reply(
        "检测到新版本可更新\n"
        f"部署方式：{mode_text}\n"
        f"分支：{branch}\n"
        f"本地：{_format_version_label(local_version, local_sha)}\n"
        f"远端：{_format_version_label(remote_version, remote_sha)}\n"
        f"{update_summary}{extra}"
    )


check_update = CommandPlugin(
    name="check_update",
    command="检查更新",
    description="check bot update from github",
    meta=PluginMeta(name="check_update", version="1.3.0", author="OpenClaw", description="检查机器人是否有新版本"),
)


@check_update.handle
async def on_check_update(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以检查更新")
        return
    try:
        local_sha, branch, remote_sha, remote_message = await _check_version_pair()
        local_version = _load_local_version()
        remote_version = await _fetch_remote_version()
    except Exception as exc:
        await ctx.reply(f"检查更新失败：{exc}")
        return

    if local_sha == remote_sha:
        _clear_pending_update()
        await ctx.reply(
            "检查完成：当前已经是最新版\n"
            f"分支：{branch}\n"
            f"版本：{_format_version_label(local_version, local_sha)}"
        )
        return

    update_summary = await _get_update_summary(local_sha, remote_sha, remote_message)
    _set_pending_update(
        branch,
        local_sha,
        remote_sha,
        remote_message,
        update_summary,
        local_version,
        remote_version,
    )
    if _can_auto_update():
        await ctx.reply(
            "检查完成：发现新版本\n"
            f"分支：{branch}\n"
            f"当前：{_format_version_label(local_version, local_sha)}\n"
            f"最新：{_format_version_label(remote_version, remote_sha)}\n"
            f"{update_summary}\n"
            "如需自动更新，请回复：确认更新\n"
            "如果暂时不更，请回复：取消更新"
        )
    else:
        await ctx.reply(
            "检查完成：发现新版本\n"
            f"分支：{branch}\n"
            f"当前：{_format_version_label(local_version, local_sha)}\n"
            f"最新：{_format_version_label(remote_version, remote_sha)}\n"
            f"{update_summary}\n"
            "当前部署支持更新检测，但不支持自动执行更新。\n"
            "建议改用 Git 工作区部署以启用自动更新。"
        )


confirm_update = CommandPlugin(
    name="confirm_update",
    command="确认更新",
    description="confirm auto update",
    meta=PluginMeta(name="confirm_update", version="1.0.0", author="OpenClaw", description="确认自动更新"),
)


@confirm_update.handle
async def on_confirm_update(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以确认更新")
        return
    pending = _get_pending_update()
    if not pending:
        await ctx.reply("当前没有待确认的更新任务，可先发送：检查更新")
        return
    if not _can_auto_update():
        await ctx.reply("当前部署方式不支持自动执行更新，请改用 Git 工作区部署。")
        return

    _start_background_update(pending.get("branch") or DEFAULT_BRANCH, pending.get("remote_sha") or "")
    await ctx.reply(
        "已开始自动更新\n"
        f"分支：{pending.get('branch') or DEFAULT_BRANCH}\n"
        f"目标版本：{_format_version_label(pending.get('remote_version') or '', pending.get('remote_sha') or '')}\n"
        "更新完成后会自动重启，并私聊通知你结果。"
    )


cancel_update = CommandPlugin(
    name="cancel_update",
    command="取消更新",
    description="cancel pending update",
    meta=PluginMeta(name="cancel_update", version="1.0.0", author="OpenClaw", description="取消待确认更新"),
)


@cancel_update.handle
async def on_cancel_update(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以取消更新")
        return
    pending = _get_pending_update()
    if not pending:
        await ctx.reply("当前没有待确认的更新任务")
        return
    _clear_pending_update()
    await ctx.reply("已取消本次待确认更新")

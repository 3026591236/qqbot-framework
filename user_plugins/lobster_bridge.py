from __future__ import annotations

import httpx

from app.auth import is_owner
from app.config import settings
from app.core.plugin import CommandPlugin, PluginMeta

plugin = None


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


def _allowed(ctx) -> bool:
    return is_owner(ctx.user_id) or ctx.role in {"admin", "owner"}


async def _post_webhook(payload: dict) -> dict:
    if not settings.lobster_webhook_url or not settings.lobster_webhook_secret:
        raise RuntimeError("Lobster webhook 未配置")
    headers = {
        "Content-Type": "application/json",
        "x-openclaw-webhook-secret": settings.lobster_webhook_secret,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(settings.lobster_webhook_url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


lobster_help = CommandPlugin(
    name="lobster_help",
    command="龙虾帮助",
    description="show lobster bridge help",
    meta=PluginMeta(name="lobster_help", version="1.0.0", author="OpenClaw", description="Lobster 桥接帮助"),
)


@lobster_help.handle
async def on_lobster_help(ctx):
    await ctx.reply(
        "龙虾桥接命令：\n"
        "- 龙虾状态\n"
        "- 龙虾任务 需求内容\n"
        "说明：该功能会把 QQ 群里的任务桥接到 OpenClaw 的 Lobster/TaskFlow。"
    )


lobster_status = CommandPlugin(
    name="lobster_status",
    command="龙虾状态",
    description="show lobster bridge status",
    meta=PluginMeta(name="lobster_status", version="1.0.0", author="OpenClaw", description="Lobster 桥接状态"),
)


@lobster_status.handle
async def on_lobster_status(ctx):
    enabled = settings.lobster_enabled and bool(settings.lobster_webhook_url and settings.lobster_webhook_secret)
    await ctx.reply(
        f"龙虾桥接状态\n"
        f"启用：{'是' if enabled else '否'}\n"
        f"Webhook：{settings.lobster_webhook_url or '-'}\n"
        f"运行时：{settings.lobster_runtime}\n"
        f"Agent：{settings.lobster_agent_id or '-'}\n"
        f"ChildSession：{settings.lobster_child_session_key or '-'}"
    )


lobster_task = CommandPlugin(
    name="lobster_task",
    command="龙虾任务",
    description="create a lobster/taskflow task from qq",
    meta=PluginMeta(name="lobster_task", version="1.0.0", author="OpenClaw", description="从 QQ 发起 Lobster 任务"),
)


@lobster_task.handle
async def on_lobster_task(ctx):
    if not _allowed(ctx):
        await ctx.reply("你没有发起龙虾任务的权限")
        return
    if not settings.lobster_enabled:
        await ctx.reply("龙虾桥接未启用，请先配置 QQBOT_LOBSTER_* 环境变量")
        return

    task_text = _extract_after_command(ctx, "龙虾任务")
    if not task_text:
        await ctx.reply("用法：龙虾任务 需求内容")
        return

    source_scope = f"group:{ctx.group_id}" if ctx.group_id else f"private:{ctx.user_id}"
    source_user = str((ctx.sender or {}).get("card") or (ctx.sender or {}).get("nickname") or ctx.user_id or "unknown")
    goal = f"来自 QQ 的 Lobster 任务：{task_text}"

    create_flow_payload = {
        "action": "create_flow",
        "controllerId": settings.lobster_controller_id,
        "goal": goal,
        "status": "running",
        "currentStep": "qq_ingress",
        "stateJson": {
            "source": "qqbot-framework",
            "scope": source_scope,
            "userId": ctx.user_id,
            "groupId": ctx.group_id,
            "userName": source_user,
            "message": task_text,
        },
    }

    try:
        created = await _post_webhook(create_flow_payload)
        flow = ((created or {}).get("result") or {}).get("flow") or {}
        flow_id = flow.get("flowId")
        revision = flow.get("revision")
        if not flow_id:
            await ctx.reply(f"龙虾任务创建失败：{created}")
            return

        run_task_payload = {
            "action": "run_task",
            "flowId": flow_id,
            "runtime": settings.lobster_runtime,
            "task": goal,
            "label": f"QQ任务 {source_user}",
            "notifyPolicy": settings.lobster_notify_policy,
        }
        if settings.lobster_agent_id:
            run_task_payload["agentId"] = settings.lobster_agent_id
        if settings.lobster_child_session_key:
            run_task_payload["childSessionKey"] = settings.lobster_child_session_key

        run_result = await _post_webhook(run_task_payload)
        task = ((run_result or {}).get("result") or {}).get("task") or {}
        task_id = task.get("taskId", "-")
        await ctx.reply(
            f"龙虾任务已提交\n"
            f"Flow ID：{flow_id}\n"
            f"Revision：{revision}\n"
            f"Task ID：{task_id}\n"
            f"内容：{task_text}"
        )
    except Exception as exc:
        await ctx.reply(f"龙虾桥接失败：{exc}")

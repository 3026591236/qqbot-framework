from app.core.plugin import CommandPlugin, PluginMeta
from app.services import daily_checkin, get_checkin_status, get_points_ranking, makeup_checkin

try:
    from user_plugins.cdk_rewards import process_checkin_reward
except Exception:
    process_checkin_reward = None

plugin = None

checkin = CommandPlugin(
    name="checkin",
    command="签到",
    description="daily checkin",
    meta=PluginMeta(name="checkin", version="2.0.0", author="OpenClaw", description="daily checkin"),
)


@checkin.handle
async def on_checkin(ctx):
    if ctx.user_id is None:
        await ctx.reply("无法识别用户")
        return

    result = daily_checkin(ctx.user_id, ctx.group_id)
    if result["ok"]:
        extra = f"（基础+{result['base_reward']}，连签加成+{result['bonus']}）" if result["bonus"] else ""
        await ctx.reply(
            f"签到成功 {extra}\n"
            f"作用域：{result['scope']}\n"
            f"本次获得：{result['gained']} 积分\n"
            f"当前积分：{result['points']}\n"
            f"连续签到：{result['streak']} 天\n"
            f"累计签到：{result['total_checkins']} 天"
        )
        if process_checkin_reward is not None:
            await process_checkin_reward(ctx, result)
    else:
        await ctx.reply(
            f"今天已经签过了\n"
            f"作用域：{result['scope']}\n"
            f"当前积分：{result['points']}\n"
            f"连续签到：{result['streak']} 天\n"
            f"累计签到：{result['total_checkins']} 天"
        )


checkin_status = CommandPlugin(
    name="checkin_status",
    command="签到状态",
    description="show checkin status",
    meta=PluginMeta(name="checkin_status", version="2.0.0", author="OpenClaw", description="show checkin status"),
)


@checkin_status.handle
async def on_checkin_status(ctx):
    if ctx.user_id is None:
        await ctx.reply("无法识别用户")
        return
    data = get_checkin_status(ctx.user_id, ctx.group_id)
    await ctx.reply(
        f"签到状态\n"
        f"作用域：{data['scope']}\n"
        f"当前积分：{data['points']}\n"
        f"连续签到：{data['streak']} 天\n"
        f"累计签到：{data['total_checkins']} 天\n"
        f"最后签到：{data['last_checkin_at'] or '-'}\n"
        f"今天是否已签到：{'是' if data['signed_today'] else '否'}\n"
        f"是否可补签：{'是' if data['can_makeup'] else '否'}"
    )


makeup = CommandPlugin(
    name="makeup_checkin",
    command="补签",
    description="make up missed checkin",
    meta=PluginMeta(name="makeup_checkin", version="2.0.0", author="OpenClaw", description="make up missed checkin"),
)


@makeup.handle
async def on_makeup(ctx):
    if ctx.user_id is None:
        await ctx.reply("无法识别用户")
        return
    result = makeup_checkin(ctx.user_id, ctx.group_id)
    if not result["ok"]:
        await ctx.reply(result["message"])
        return
    extra = f"，连签加成 +{result['bonus']}" if result['bonus'] else ""
    await ctx.reply(
        f"补签成功\n"
        f"作用域：{result['scope']}\n"
        f"扣除积分：{result['cost']}\n"
        f"补签获得：{result['gained']} 积分{extra}\n"
        f"当前积分：{result['points']}\n"
        f"连续签到：{result['streak']} 天\n"
        f"累计签到：{result['total_checkins']} 天"
    )


checkin_rank = CommandPlugin(
    name="checkin_rank",
    command="签到排行",
    description="show points/checkin ranking",
    meta=PluginMeta(name="checkin_rank", version="2.0.0", author="OpenClaw", description="show points/checkin ranking"),
)


@checkin_rank.handle
async def on_checkin_rank(ctx):
    text = ctx.text.strip()
    parts = text.split(maxsplit=1)
    limit = 10
    if len(parts) > 1 and parts[1].strip().isdigit():
        limit = max(1, min(20, int(parts[1].strip())))
    rows = get_points_ranking(ctx.group_id, limit)
    if not rows:
        await ctx.reply("当前还没有签到排行数据")
        return
    lines = []
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"{idx}. {row['user_id']} | 积分:{row['points']} | 连签:{row['checkin_streak']} | 累签:{row['total_checkins']}"
        )
    scope = "本群" if ctx.group_id else "私聊"
    await ctx.reply(f"{scope}签到排行：\n" + "\n".join(lines))

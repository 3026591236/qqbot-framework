from app.core.plugin import CommandPlugin, PluginMeta
from app.services import get_checkin_status, get_points

plugin = CommandPlugin(
    name="points",
    command="积分",
    description="show points",
    meta=PluginMeta(name="points", version="2.0.0", author="OpenClaw", description="show points"),
)


@plugin.handle
async def on_points(ctx):
    if ctx.user_id is None:
        await ctx.reply("无法识别用户")
        return

    points = get_points(ctx.user_id, ctx.group_id)
    status = get_checkin_status(ctx.user_id, ctx.group_id)
    await ctx.reply(
        f"当前积分：{points}\n"
        f"作用域：{status['scope']}\n"
        f"连续签到：{status['streak']} 天\n"
        f"累计签到：{status['total_checkins']} 天"
    )

from app.core.plugin import CommandPlugin, PluginMeta

plugin = CommandPlugin(
    name="ping",
    command="/ping",
    description="health check",
    meta=PluginMeta(name="ping", version="1.0.0", author="OpenClaw", description="health check"),
)


@plugin.handle
async def on_ping(ctx):
    await ctx.reply("pong")

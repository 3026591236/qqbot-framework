from app.core.plugin import CommandPlugin, PluginMeta

plugin = CommandPlugin(
    name="echo",
    command="/echo",
    description="echo text",
    meta=PluginMeta(name="echo", version="1.0.0", author="OpenClaw", description="echo text"),
)


@plugin.handle
async def on_echo(ctx):
    content = ctx.text[len("/echo"):].strip()
    if not content:
        await ctx.reply("用法：/echo 你要我复读的内容")
        return
    await ctx.reply(content)

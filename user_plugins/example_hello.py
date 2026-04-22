from app.core.plugin import CommandPlugin, PluginMeta

plugin = CommandPlugin(
    name="example_hello",
    command="/hello",
    description="example user plugin",
    meta=PluginMeta(
        name="example_hello",
        version="1.0.0",
        author="OpenClaw",
        description="示例用户插件",
        dependencies=[],
    ),
)


@plugin.handle
async def on_hello(ctx):
    await ctx.reply("你好，这是 user_plugins 目录中的示例插件")

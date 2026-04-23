from app.core.plugin import CommandPlugin, PluginMeta


def _menu_text() -> str:
    return (
        "╭─── ✦ QQ机器人功能菜单 ✦ ───╮\n"
        "│                              │\n"
        "│  ◇ 基础功能                  │\n"
        "│ 〔通用菜单〕 〔签到菜单〕     │\n"
        "│ 〔AI菜单〕    〔插件菜单〕     │\n"
        "│                              │\n"
        "│  ◇ 进阶功能                  │\n"
        "│ 〔群管菜单〕 〔卡片菜单〕     │\n"
        "│ 〔发卡菜单〕 〔语录菜单〕     │\n"
        "│ 〔龙虾菜单〕                 │\n"
        "│                              │\n"
        "│  ◇ 快捷入口                  │\n"
        "│  菜单   help   ping          │\n"
        "│                              │\n"
        "│  ◇ 使用方式                  │\n"
        "│  直接发送上面的菜单名即可    │\n"
        "│  例如：AI菜单 / 群管菜单     │\n"
        "│                              │\n"
        "│  ◇ 小提示                    │\n"
        "│  输错命令会自动提示接近功能  │\n"
        "╰──────────────────────────────╯"
    )


plugin = CommandPlugin(
    name="help",
    command="/help",
    description="show help",
    meta=PluginMeta(name="help", version="1.1.0", author="OpenClaw", description="show help menu"),
)


@plugin.handle
async def on_help(ctx):
    await ctx.reply(_menu_text())


menu = CommandPlugin(
    name="menu",
    command="菜单",
    description="show full menu",
    meta=PluginMeta(name="menu", version="1.1.0", author="OpenClaw", description="show full menu"),
)


@menu.handle
async def on_menu(ctx):
    await ctx.reply(_menu_text())


common_menu = CommandPlugin(
    name="common_menu",
    command="通用菜单",
    description="show common commands",
    meta=PluginMeta(name="common_menu", version="1.1.0", author="OpenClaw", description="show common commands"),
)


@common_menu.handle
async def on_common_menu(ctx):
    await ctx.reply(
        "通用功能\n"
        "- ping：检查机器人是否在线\n"
        "- help / 菜单：查看总菜单\n"
        "- echo 内容：复读你发送的内容\n"
        "\n"
        "示例：\n"
        "- ping\n"
        "- echo 你好"
    )


checkin_menu = CommandPlugin(
    name="checkin_menu",
    command="签到菜单",
    description="show checkin commands",
    meta=PluginMeta(name="checkin_menu", version="1.1.0", author="OpenClaw", description="show checkin commands"),
)


@checkin_menu.handle
async def on_checkin_menu(ctx):
    await ctx.reply(
        "签到积分功能\n"
        "- 签到：每日签到领积分\n"
        "- 签到状态：查看今日是否签到、连签情况\n"
        "- 补签：补昨天漏掉的签到\n"
        "- 签到排行 [数量]：查看签到/积分排行\n"
        "- 积分：查看自己的积分信息\n"
        "- 发卡菜单：查看签到奖励/CDK/邀请奖励相关命令\n"
        "- 今日水群前三：查看本群当天消息数前三名\n"
        "- 昨日水群前三：查看本群昨天消息数前三名\n"
        "- 今日水群排行：查看本群当天消息排行 Top10\n"
        "- 开启水群前三奖励 第一名卡池 第二名卡池 第三名卡池：前三名分开发放\n"
        "- 关闭水群前三奖励\n"
        "- 水群前三奖励状态\n"
        "\n"
        "示例：\n"
        "- 签到\n"
        "- 签到状态\n"
        "- 补签\n"
        "- 签到排行 10\n"
        "- 积分"
    )


ai_menu = CommandPlugin(
    name="ai_menu",
    command="AI菜单",
    description="show ai relay commands",
    meta=PluginMeta(name="ai_menu", version="1.1.0", author="OpenClaw", description="show ai relay commands"),
)


@ai_menu.handle
async def on_ai_menu(ctx):
    await ctx.reply(
        "AI中转站功能\n"
        "- AI帮助：查看 AI 功能帮助\n"
        "- AI状态：查看当前中转站配置状态\n"
        "- 配置AI中转站 地址 Key：配置中转站（主人私聊）\n"
        "- AI模型列表：获取可用模型列表（主人私聊）\n"
        "- 选择AI模型 序号：按编号选择模型\n"
        "- 切换AI模型 模型名：直接按模型名切换\n"
        "- AI 问题：直接提问\n"
        "- 问AI 问题：提问别名\n"
        "\n"
        "推荐流程：\n"
        "1. 配置AI中转站 https://你的地址/v1 sk-xxxx\n"
        "2. AI模型列表\n"
        "3. 选择AI模型 1\n"
        "4. AI 你好"
    )


plugin_menu = CommandPlugin(
    name="plugin_menu",
    command="插件菜单",
    description="show plugin management commands",
    meta=PluginMeta(name="plugin_menu", version="1.1.0", author="OpenClaw", description="show plugin management commands"),
)


@plugin_menu.handle
async def on_plugin_menu(ctx):
    await ctx.reply(
        "插件管理功能（主人）\n"
        "- 插件列表：查看所有已登记插件\n"
        "- 插件详情 插件名：查看某个插件的详细信息\n"
        "- 启用插件 插件名：启用插件\n"
        "- 禁用插件 插件名：禁用插件\n"
        "- 插件市场：查看市场可安装插件\n"
        "- 安装插件 插件名：从插件商店下载安装到 user_plugins（主人）\n"
        "- 检查更新：检查 GitHub 是否有新版\n"
        "- 更新状态：查看当前本地与远端版本状态\n"
        "- 确认更新：确认后自动执行更新（仅 git 部署）\n"
        "- 取消更新：取消当前待确认更新\n"
        "- 自动提醒：发现 GitHub 新版本时会私聊通知主人\n"
        "- 入群邀请状态：查看当前待处理入群邀请\n"
        "- 同意入群：同意当前待处理入群邀请\n"
        "- 拒绝入群：拒绝当前待处理入群邀请\n"
        "- 卡片模式：查看当前全局卡片模式\n"
        "- 切换卡片模式 文字/图片：切换全局卡片输出\n"
        "\n"
        "示例：\n"
        "- 插件列表\n"
        "- 插件详情 ai_relay_help\n"
        "- 启用插件 example_hello\n"
        "- 禁用插件 example_hello\n"
        "- 检查更新\n"
        "- 更新状态\n"
        "- 确认更新\n"
        "- 取消更新\n"
        "- 入群邀请状态\n"
        "- 同意入群\n"
        "- 拒绝入群\n"
        "- 卡片模式\n"
        "- 切换卡片模式 文字/图片"
    )


group_menu = CommandPlugin(
    name="group_menu",
    command="群管菜单",
    description="show group admin commands",
    meta=PluginMeta(name="group_menu", version="1.1.0", author="OpenClaw", description="show group admin commands"),
)


@group_menu.handle
async def on_group_menu(ctx):
    await ctx.reply(
        "高级群管功能\n"
        "- 群管帮助：查看完整群管帮助\n"
        "- 群管状态：查看当前群管配置\n"
        "- 群管 开 / 关\n"
        "- 开启自动撤回 秒数 / 开始自动撤回 秒数\n"
        "- 关闭自动撤回 / 停止自动撤回 / 自动撤回状态\n"
        "- 禁言 @某人 10m / 解禁 @某人\n"
        "- 全员禁言 开 / 关\n"
        "- 警告 @某人 原因\n"
        "- 警告记录 @某人\n"
        "- 添加违禁词 词语\n"
        "- 删除违禁词 词语\n"
        "- 白名单 @某人 / 取消白名单 @某人\n"
        "- 欢迎 开/关 / 设置欢迎词 内容\n"
        "- 退群通知 开/关 / 撤回通知 开/关\n"
        "- 链接审核 开/关\n"
        "- 刷屏检测 开/关 / 刷屏阈值 次数 / 刷屏窗口 秒数\n"
        "- 群管日志 [数量]\n"
        "\n"
        "说明：群管功能一般需要群管理员或机器人主人权限。"
    )


card_menu = CommandPlugin(
    name="card_menu",
    command="卡片菜单",
    description="show card commands",
    meta=PluginMeta(name="card_menu", version="1.1.0", author="OpenClaw", description="show card commands"),
)


@card_menu.handle
async def on_card_menu(ctx):
    await ctx.reply(
        "卡片/伪卡片功能\n"
        "- 卡片风格：查看当前图片卡片风格\n"
        "- 切换卡片风格 风格名：切换图片卡片风格（主人，支持中文）\n"
        "  可选示例：浅色 / 深色 / 紧凑 / 极简 / 樱粉 / 薄荷 / 纸质 / 黑金\n"
        "- 卡片帮助\n"
        "- 测试伪卡片\n"
        "- 发伪卡片 标题|内容|链接\n"
        "- 测试卡片json\n"
        "- 测试卡片xml\n"
        "- 发json卡片 标题|内容|链接\n"
        "- 发xml卡片 标题|内容|链接\n"
        "- 测试图片卡\n"
        "- 卡片模式\n"
        "- 切换卡片模式 文字/图片（全局）\n"
        "- 本群切换卡片模式 文字/图片\n"
        "\n"
        "说明：当前 QQ 链路下官方 JSON/XML 卡片不稳定；现在支持按群单独切换图片/文字卡片模式。"
    )


reward_menu = CommandPlugin(
    name="reward_menu",
    command="发卡菜单",
    description="show cdk reward commands",
    meta=PluginMeta(name="reward_menu", version="1.0.0", author="OpenClaw", description="show cdk reward commands"),
)


@reward_menu.handle
async def on_reward_menu(ctx):
    await ctx.reply(
        "发卡奖励功能\n"
        "- 发卡帮助\n"
        "- 设置发卡管理员 @某人/QQ号\n"
        "- 删除发卡管理员 @某人/QQ号\n"
        "- 发卡管理员列表\n"
        "- 设置签到首日奖励 卡池名/关闭\n"
        "- 设置连续签到奖励 天数 卡池名\n"
        "- 删除连续签到奖励 天数\n"
        "- 设置邀请奖励 人数 卡池名\n"
        "- 删除邀请奖励 人数\n"
        "- 添加CDK 卡池名 CDK（群内）\n"
        "- 添加CDK 群号 卡池名 CDK（私聊）\n"
        "- 删除卡池 卡池名\n"
        "- 删除CDK 卡池名 CDK\n"
        "- 卡池状态 [卡池名]\n"
        "- 邀请统计 [@某人/QQ号]\n"
        "- 开启随机发言发卡 卡池名 [每几分钟一次，默认10]\n"
        "- 关闭随机发言发卡\n"
        "- 随机发言发卡状态\n"
        "\n"
        "说明：签到奖励会群内提示、CDK 私聊发放；同一奖励规则会自动防重复发放。支持公共卡密：添加一次后可反复发放。"
    )


quote_menu = CommandPlugin(
    name="quote_menu",
    command="语录菜单",
    description="show quote commands",
    meta=PluginMeta(name="quote_menu", version="1.1.0", author="OpenClaw", description="show quote commands"),
)


@quote_menu.handle
async def on_quote_menu(ctx):
    await ctx.reply(
        "语录馆功能\n"
        "- 语录帮助\n"
        "- 收录语录 一段内容\n"
        "- 今日语录\n"
        "- 随机语录\n"
        "- 语录列表 [数量]\n"
        "- 删除语录 ID（管理员/主人）\n"
        "\n"
        "示例：\n"
        "- 收录语录 今天也要加油\n"
        "- 随机语录\n"
        "- 语录列表 10"
    )


lobster_menu = CommandPlugin(
    name="lobster_menu",
    command="龙虾菜单",
    description="show lobster bridge commands",
    meta=PluginMeta(name="lobster_menu", version="1.1.0", author="OpenClaw", description="show lobster bridge commands"),
)


@lobster_menu.handle
async def on_lobster_menu(ctx):
    await ctx.reply(
        "龙虾桥接功能\n"
        "- 龙虾帮助\n"
        "- 龙虾状态\n"
        "- 龙虾任务 需求内容\n"
        "\n"
        "说明：这个功能需要先配置 OpenClaw Webhook / TaskFlow 相关参数，否则只是占位能力。"
    )

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches

from app.core.plugin import PluginMeta

KNOWN_PREFIXES = [
    "菜单",
    "通用菜单",
    "签到菜单",
    "AI菜单",
    "插件菜单",
    "群管菜单",
    "卡片菜单",
    "发卡菜单",
    "发卡帮助",
    "设置发卡管理员",
    "删除发卡管理员",
    "发卡管理员列表",
    "设置签到首日奖励",
    "设置连续签到奖励",
    "删除连续签到奖励",
    "设置邀请奖励",
    "删除邀请奖励",
    "添加CDK",
    "卡池状态",
    "邀请统计",
    "今日水群前三",
    "昨日水群前三",
    "今日水群排行",
    "开启水群前三奖励",
    "关闭水群前三奖励",
    "水群前三奖励状态",
    "开启自动撤回",
    "开始自动撤回",
    "关闭自动撤回",
    "停止自动撤回",
    "自动撤回状态",
    "语录菜单",
    "龙虾菜单",
    "ping",
    "/ping",
    "help",
    "/help",
    "echo",
    "/echo",
    "签到",
    "签到状态",
    "补签",
    "签到排行",
    "积分",
    "插件列表",
    "插件详情",
    "启用插件",
    "禁用插件",
    "插件市场",
    "安装插件",
    "群管帮助",
    "群管状态",
    "卡片帮助",
    "卡片风格",
    "切换卡片风格",
    "发伪卡片",
    "测试伪卡片",
    "AI帮助",
    "AI状态",
    "AI",
    "问AI",
    "配置AI中转站",
    "AI模型列表",
    "选择AI模型",
    "切换AI模型",
    "龙虾帮助",
    "龙虾状态",
    "龙虾任务",
    "语录帮助",
    "收录语录",
    "今日语录",
    "随机语录",
    "语录列表",
    "删除语录",
]


@dataclass
class UnknownCommandHintPlugin:
    name: str = "unknown_command_hint"
    description: str = "hint user when command looks unknown"
    meta: PluginMeta = PluginMeta(
        name="unknown_command_hint",
        version="1.3.0",
        author="OpenClaw",
        description="hint user when command looks unknown",
    )

    async def dispatch(self, ctx) -> bool:
        text = _normalize(ctx.text)
        if not text:
            return False

        command_like = (
            text.startswith("/")
            or text.startswith("插件")
            or text.startswith("群管")
            or text.startswith("签到")
            or text.startswith("积分")
            or text.startswith("今日水群")
            or text.startswith("卡片")
            or text.startswith("发卡")
            or text.startswith("开启自动撤回")
            or text.startswith("开始自动撤回")
            or text.startswith("关闭自动撤回")
            or text.startswith("停止自动撤回")
            or text.startswith("自动撤回")
            or text.startswith("发")
            or text.startswith("AI")
            or text.startswith("问AI")
            or text.startswith("配置AI中转站")
            or text.startswith("选择AI模型")
            or text.startswith("切换AI模型")
            or text.startswith("龙虾")
            or text.startswith("语录")
            or text.startswith("收录语录")
            or text.startswith("菜单")
            or text.startswith("通用菜单")
            or text.startswith("签到菜单")
            or text.startswith("AI菜单")
            or text.startswith("插件菜单")
            or text.startswith("群管菜单")
            or text.startswith("卡片菜单")
            or text.startswith("语录菜单")
            or text.startswith("龙虾菜单")
            or text in {"help", "ping", "echo"}
        )
        if not command_like:
            return False

        for item in KNOWN_PREFIXES:
            if text == item or text.startswith(item + " "):
                return False

        token = _first_token(text)
        candidates = get_close_matches(token, KNOWN_PREFIXES, n=5, cutoff=0.45)
        if not candidates and len(text) <= 6:
            candidates = get_close_matches(text, KNOWN_PREFIXES, n=5, cutoff=0.4)

        if candidates:
            await ctx.reply(
                "这个命令我没认出来。\n"
                f"你是不是想用：{' / '.join(candidates)}\n"
                "如果你不确定，可以直接发：菜单"
            )
            return True

        await ctx.reply(
            "这个命令我没认出来。\n"
            "你可以直接发：菜单\n"
            "常用命令：ping、签到、积分、今日水群前三、AI帮助、插件列表、群管帮助"
        )
        return True


plugin = UnknownCommandHintPlugin()


def _normalize(text: str) -> str:
    return (text or "").strip()


def _first_token(text: str) -> str:
    return _normalize(text).split(maxsplit=1)[0] if _normalize(text) else ""

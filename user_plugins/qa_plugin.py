"""
模糊问答插件 - 支持关键词模糊匹配自动回复

功能：
- 基于关键词的模糊匹配问答
- 支持精确匹配和模糊匹配两种模式
- 可动态配置问答对（通过 data/qa_pairs.json）
- 支持启用/禁用单个问答对
- 监听所有群消息，自动触发匹配

使用方法：
1. 编辑 data/qa_pairs.json 添加/修改问答对
2. 重启机器人或运行 /问答重载 重新加载
3. 在群内发送任意消息，如果包含关键词即触发回复

管理命令：
- /问答添加 关键词 回复内容 [精确/模糊]
- /问答列表
- /问答删除 <ID>
- /问答切换 <ID>
- /问答重载
- /问答菜单
"""

import json
import re
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher

from app.core.plugin import RegexPlugin, PluginMeta
from app.core.context import MessageContext

# 插件元数据 - 使用正则表达式匹配所有消息
plugin = RegexPlugin(
    name="qa_fuzzy_plugin",
    pattern=r"^(?!\s*(?:检查更新|更新状态|确认更新|取消更新|OpenClaw帮助|OpenClaw状态|设置OpenClaw管理员|删除OpenClaw管理员|OpenClaw管理员列表|配置OpenClaw桥接|爪爪|小小)(?:\s|$)).+",
    description="模糊问答自动回复插件",
    meta=PluginMeta(
        name="模糊问答",
        version="1.0.0",
        author="OpenClaw",
        description="基于关键词模糊匹配的自动问答回复插件",
        dependencies=[],
    ),
)


class FuzzyQAPlugin:
    """模糊问答核心逻辑类"""

    def __init__(self):
        self.data_path = Path(__file__).parent.parent / "data" / "qa_pairs.json"
        self.qa_pairs: List[Dict[str, Any]] = []
        self.settings: Dict[str, Any] = {}
        self._load_data()

    def _load_data(self):
        """加载问答数据"""
        try:
            if self.data_path.exists():
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.qa_pairs = data.get("qa_pairs", [])
                    self.settings = data.get("settings", {
                        "default_match_threshold": 0.6,
                        "enable_exact_match": True,
                        "enable_fuzzy_match": True,
                        "max_results": 1,
                        "response_delay_ms": 500
                    })
            else:
                self.qa_pairs = []
                self.settings = {
                    "default_match_threshold": 0.6,
                    "enable_exact_match": True,
                    "enable_fuzzy_match": True,
                    "max_results": 1,
                    "response_delay_ms": 500
                }
        except Exception as e:
            print(f"[FuzzyQA] 加载数据失败：{e}")
            self.qa_pairs = []
            self.settings = {}

    def reload(self):
        """重新加载数据"""
        self._load_data()
        return f"已重新加载 {len(self.qa_pairs)} 条问答配置"

    def calculate_similarity(self, text: str, keyword: str) -> float:
        """计算文本与关键词的相似度"""
        text_clean = re.sub(r'[^\w\s]', '', text).lower()
        keyword_clean = re.sub(r'[^\w\s]', '', keyword).lower()
        return SequenceMatcher(None, text_clean, keyword_clean).ratio()

    def find_matching_qa(self, message: str) -> Optional[Dict[str, Any]]:
        """查找匹配的问答对"""
        threshold = self.settings.get("default_match_threshold", 0.6)

        for qa in self.qa_pairs:
            if not qa.get("enabled", True):
                continue

            keywords = qa.get("keywords", [])
            match_mode = qa.get("match_mode", "fuzzy")

            for keyword in keywords:
                if match_mode == "exact":
                    # 精确匹配：关键词必须完整出现在消息中
                    if keyword in message:
                        return qa
                else:
                    # 模糊匹配：关键词部分匹配或相似度足够
                    if keyword in message:
                        return qa
                    similarity = self.calculate_similarity(message, keyword)
                    if similarity >= threshold:
                        return qa

        return None

    def get_all_qa_pairs(self) -> List[Dict[str, Any]]:
        """获取所有问答对"""
        return self.qa_pairs

    def add_qa_pair(self, keywords: List[str], response: str, match_mode: str = "fuzzy") -> str:
        """添加新的问答对"""
        qa_id = f"qa_{len(self.qa_pairs) + 1:03d}"
        new_pair = {
            "id": qa_id,
            "keywords": keywords,
            "response": response,
            "enabled": True,
            "match_mode": match_mode,
            "created_at": "2025-01-01T00:00:00Z"
        }
        self.qa_pairs.append(new_pair)
        self._save_data()
        return f"已添加问答对 {qa_id}"

    def remove_qa_pair(self, qa_id: str) -> str:
        """删除问答对"""
        for i, qa in enumerate(self.qa_pairs):
            if qa.get("id") == qa_id:
                self.qa_pairs.pop(i)
                self._save_data()
                return f"已删除问答对 {qa_id}"
        return f"未找到问答对 {qa_id}"

    def toggle_qa_pair(self, qa_id: str) -> str:
        """切换问答对启用状态"""
        for qa in self.qa_pairs:
            if qa.get("id") == qa_id:
                qa["enabled"] = not qa["enabled"]
                self._save_data()
                status = "启用" if qa["enabled"] else "禁用"
                return f"已{status}问答对 {qa_id}"
        return f"未找到问答对 {qa_id}"

    def _save_data(self):
        """保存数据到文件"""
        try:
            data = {
                "version": "1.0.0",
                "description": "模糊问答配置数据",
                "qa_pairs": self.qa_pairs,
                "settings": self.settings
            }
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[FuzzyQA] 保存数据失败：{e}")


# 创建插件实例
qa_plugin = FuzzyQAPlugin()

RESERVED_PREFIXES = [
    "检查更新", "更新状态", "确认更新", "取消更新",
    "OpenClaw帮助", "OpenClaw状态", "设置OpenClaw管理员", "删除OpenClaw管理员", "OpenClaw管理员列表", "配置OpenClaw桥接",
    "爪爪", "小小",
]


@plugin.handle
async def on_message(ctx: MessageContext):
    """极速抢答 - 零日志，纯速度"""
    message_text = ctx.text

    # 1. 优先处理命令
    if message_text.startswith("/问答"):
        await _handle_command(ctx, message_text)
        return True

    # 2. 跳过命令
    if message_text.startswith("/"):
        return False

    # 3. 跳过系统/桥接保留命令
    for prefix in RESERVED_PREFIXES:
        if message_text == prefix or message_text.startswith(prefix + " "):
            return False

    # 4. 跳过包含"问答"的消息
    if "问答" in message_text:
        return False

    # 5. 极速匹配
    matched_qa = qa_plugin.find_matching_qa(message_text)

    if matched_qa:
        response = matched_qa.get("response", "")
        # 尝试直接调用 API，不等待任何日志
        try:
            if ctx.api and ctx.group_id:
                # 使用 asyncio.create_task 异步发送，不阻塞当前流程
                asyncio.create_task(ctx.api.send_group_msg(group_id=ctx.group_id, message=response))
                return True
        except Exception:
            pass
        return False
    return False


async def _handle_command(ctx: MessageContext, message_text: str):
    """处理问答管理命令"""
    parts = message_text.split(maxsplit=1)
    if len(parts) < 2:
        await _show_menu(ctx)
        return

    cmd = parts[0]
    args = parts[1].strip()

    if cmd == "/问答添加":
        await _cmd_add(ctx, args)
    elif cmd == "/问答列表":
        await _cmd_list(ctx)
    elif cmd == "/问答删除":
        await _cmd_remove(ctx, args)
    elif cmd == "/问答切换":
        await _cmd_toggle(ctx, args)
    elif cmd == "/问答重载":
        await _cmd_reload(ctx)
    elif cmd == "/问答菜单":
        await _show_menu(ctx)
    else:
        await _show_menu(ctx)


async def _show_menu(ctx: MessageContext):
    """显示问答管理菜单"""
    menu_text = """
🤖 **模糊问答管理菜单**

**自动回复功能**：
在群内发送包含关键词的消息，机器人会自动匹配并回复

**管理命令**：
1️⃣ `/问答添加 关键词 回复内容 [精确/模糊]` - 添加新问答
2️⃣ `/问答列表` - 查看所有问答对
3️⃣ `/问答删除 <ID>` - 删除指定问答
4️⃣ `/问答切换 <ID>` - 启用/禁用问答
5️⃣ `/问答重载` - 重新加载配置
6️⃣ `/问答菜单` - 显示此菜单

**快捷示例**：
`/问答添加 客服，人工 请联系客服 QQ: 123456 模糊`
`/问答添加 下载 官方下载地址：https://example.com 精确`

**配置文件**：
📁 `data/qa_pairs.json`

💡 提示：修改 JSON 文件后，使用 `/问答重载` 生效
"""
    await ctx.reply(menu_text)


async def _cmd_add(ctx: MessageContext, args: str):
    """添加问答对命令"""
    parts = args.rsplit(maxsplit=2)
    if len(parts) < 2:
        await ctx.reply("📝 **用法**：`/问答添加 关键词 回复内容 [精确/模糊]`\n\n**示例**：\n`/问答添加 攻略，怎么玩 这里是攻略内容 模糊`")
        return

    keywords_str = parts[0]
    response = parts[1]
    mode = parts[2] if len(parts) > 2 else "fuzzy"

    if mode in ["精确", "exact"]:
        mode = "exact"
    else:
        mode = "fuzzy"

    keyword_list = [k.strip() for k in keywords_str.split(",")]
    result = qa_plugin.add_qa_pair(keyword_list, response, mode)
    await ctx.reply(f"✅ {result}")


async def _cmd_list(ctx: MessageContext):
    """列出问答对命令"""
    pairs = qa_plugin.get_all_qa_pairs()
    if not pairs:
        await ctx.reply("📭 暂无问答配置")
        return

    result = "📚 **问答列表**\n\n"
    for i, qa in enumerate(pairs[:10], 1):
        status = "✅" if qa.get("enabled", True) else "❌"
        keywords = ", ".join(qa.get("keywords", [])[:3])
        result += f"{i}. {status} {qa.get('id')}: {keywords}\n"

    if len(pairs) > 10:
        result += f"\n...还有 {len(pairs) - 10} 条"

    await ctx.reply(result)


async def _cmd_remove(ctx: MessageContext, qa_id: str):
    """删除问答对命令"""
    if not qa_id:
        await ctx.reply("📝 **用法**：`/问答删除 <问答 ID>`\n\n**示例**：\n`/问答删除 qa_001`")
        return

    result = qa_plugin.remove_qa_pair(qa_id)
    await ctx.reply(f"✅ {result}")


async def _cmd_toggle(ctx: MessageContext, qa_id: str):
    """切换问答对启用状态命令"""
    if not qa_id:
        await ctx.reply("📝 **用法**：`/问答切换 <问答 ID>`\n\n**示例**：\n`/问答切换 qa_001`")
        return

    result = qa_plugin.toggle_qa_pair(qa_id)
    await ctx.reply(f"✅ {result}")


async def _cmd_reload(ctx: MessageContext):
    """重新加载配置命令"""
    result = qa_plugin.reload()
    await ctx.reply(f"✅ {result}")

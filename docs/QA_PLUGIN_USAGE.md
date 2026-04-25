# 模糊问答插件使用指南

## 功能简介

模糊问答插件 (`qa_plugin.py`) 为机器人提供了基于关键词的自动问答回复功能，支持：

- **模糊匹配**：消息中包含关键词即可触发回复
- **精确匹配**：可配置为必须完全匹配关键词
- **动态配置**：通过 JSON 文件管理问答对，无需重启
- **启用/禁用**：可单独控制每个问答对的开关

## 安装与启用

1. 插件文件已创建：`user_plugins/qa_plugin.py`
2. 数据文件已创建：`data/qa_pairs.json`
3. 重启机器人或运行以下命令加载插件：

```bash
# 在机器人所在目录
./run.sh
# 或
python -m app.main
```

## 使用方法

### 自动回复

在群内发送包含关键词的消息，机器人会自动匹配并回复。

**示例**：
- 用户发送："这个游戏的**攻略**在哪里？"
- 机器人回复：预设的攻略内容

### 管理命令

#### 添加问答对
```
/qa add <关键词> <回复内容> [exact|fuzzy]
```

**示例**：
```
/qa add 下载，安装包 官方下载地址：https://example.com fuzzy
/qa add 客服 exact 请联系客服 QQ: 123456
```

- `关键词`：多个关键词用逗号分隔
- `回复内容`：支持 Markdown 格式
- `模式`：`fuzzy`（模糊匹配，默认）或 `exact`（精确匹配）

#### 列出所有问答对
```
/qa list
```

显示所有配置的问答对及其状态。

#### 删除问答对
```
/qa remove <问答 ID>
```

**示例**：
```
/qa remove qa_001
```

#### 切换启用状态
```
/qa toggle <问答 ID>
```

**示例**：
```
/qa toggle qa_002
```

#### 重新加载配置
```
/qa reload
```

重新从 `data/qa_pairs.json` 加载配置，无需重启机器人。

#### 显示帮助
```
/qa help
```

## 配置文件说明

配置文件路径：`data/qa_pairs.json`

### 结构示例

```json
{
  "version": "1.0.0",
  "description": "模糊问答配置数据",
  "qa_pairs": [
    {
      "id": "qa_001",
      "keywords": ["攻略", "怎么玩", "新手指南"],
      "response": "📖 **游戏攻略**\n\n这里是攻略内容...",
      "enabled": true,
      "match_mode": "fuzzy",
      "created_at": "2025-01-01T00:00:00Z"
    }
  ],
  "settings": {
    "default_match_threshold": 0.6,
    "enable_exact_match": true,
    "enable_fuzzy_match": true,
    "max_results": 1,
    "response_delay_ms": 500
  }
}
```

### 字段说明

#### qa_pairs 数组项
- `id`: 问答对唯一标识（自动生成）
- `keywords`: 关键词列表，任一匹配即可触发
- `response`: 回复内容，支持 Markdown
- `enabled`: 是否启用（true/false）
- `match_mode`: 匹配模式（`fuzzy` 或 `exact`）
- `created_at`: 创建时间

#### settings 配置项
- `default_match_threshold`: 模糊匹配阈值（0-1，默认 0.6）
- `enable_exact_match`: 是否启用精确匹配
- `enable_fuzzy_match`: 是否启用模糊匹配
- `max_results`: 最多返回匹配结果数
- `response_delay_ms`: 回复延迟（毫秒）

## 手动编辑配置

### 添加新问答对

1. 打开 `data/qa_pairs.json`
2. 在 `qa_pairs` 数组中添加新项：

```json
{
  "keywords": ["新关键词 1", "新关键词 2"],
  "response": "新的回复内容",
  "enabled": true,
  "match_mode": "fuzzy"
}
```

3. 保存文件
4. 运行 `/qa reload` 重新加载

### 禁用某个问答对

将 `enabled` 改为 `false`：

```json
{
  "id": "qa_001",
  "keywords": ["攻略"],
  "response": "...",
  "enabled": false,
  ...
}
```

## 注意事项

1. **关键词匹配**：
   - 模糊匹配：消息中包含关键词即可触发
   - 精确匹配：关键词必须完全匹配

2. **回复优先级**：
   - 多个匹配时，返回相似度最高的
   - 可通过 `max_results` 调整

3. **性能考虑**：
   - 问答对数量较多时，建议设置合理的匹配阈值
   - 禁用不常用的问答对可提升性能

4. **安全提示**：
   - 回复内容不要包含敏感信息
   - 谨慎开放管理员权限

## 故障排查

### 插件未生效
1. 检查 `user_plugins/qa_plugin.py` 是否存在
2. 运行 `/plugin list` 确认插件已加载
3. 运行 `/qa reload` 重新加载配置

### 匹配不准确
1. 调整 `default_match_threshold` 值（0.5-0.8 之间尝试）
2. 增加更多关键词覆盖不同表达方式
3. 考虑使用 `exact` 模式进行精确匹配

### 回复内容为空
1. 检查 `qa_pairs.json` 格式是否正确
2. 确认问答对的 `enabled` 为 `true`
3. 运行 `/qa list` 查看配置是否加载成功

## 高级用法

### 组合关键词
```json
{
  "keywords": ["怎么下载", "下载地址", "安装包在哪"],
  "response": "下载地址：https://example.com"
}
```

### 多行回复
```json
{
  "keywords": ["规则"],
  "response": "📋 **游戏规则**\n\n1. 第一条规则\n2. 第二条规则\n3. 第三条规则"
}
```

### 包含链接和格式
```json
{
  "keywords": ["官网"],
  "response": "🌐 **官方网站**\n\n- 官网：https://example.com\n- 论坛：https://forum.example.com\n- 客服 QQ: 123456"
}
```

## 更新日志

### v1.0.0 (2025-01-01)
- 初始版本发布
- 支持模糊匹配和精确匹配
- 提供完整的管理命令
- 支持动态配置加载

---

如有问题，请在群内反馈或查看 `user_plugins/qa_plugin.py` 源码。

# 最终交付说明

这是当前整理后的可交付 QQ 机器人框架发布版说明。

## 一、交付目标

本交付物的目标是提供一套：

- 可部署
- 可迁移
- 可扩展
- 支持插件系统
- 支持 QQ 扫码登录接入
- 支持群聊与群管理
- 具备基础业务插件能力

的 QQ 机器人框架。

## 二、当前推荐方案

- 业务框架：`qqbot-framework`
- QQ 适配器：`NapCat`
- 协议：`OneBot v11`
- 消息 API：HTTP
- 事件上报：HTTP POST

## 三、发布包

发布压缩包：

```text
qqbot-framework-release.tar.gz
```

## 四、发布包内容

已纳入发布包：

- `app/`
- `deploy/`
- `docs/`
- `scripts/`
- `user_plugins/`
- `README.md`
- `DEPLOY_FINAL.md`
- `.env.example`
- `Dockerfile`
- `docker-compose.yml`
- `install_plugin.py`
- `market.example.json`
- `requirements.txt`
- `run.sh`

已尽量排除运行时内容：

- `.env`
- `.venv`
- `logs/`
- `data/`
- `ntqq/`
- `napcat/cache/`
- 本地二维码缓存
- 当前服务器登录态

## 五、核心能力

当前已经具备：

- OneBot v11 事件接收
- HTTP API 回消息
- 插件自动发现与自动加载
- 插件启用 / 禁用 / 升级 / 卸载
- 主人权限控制
- 插件市场索引
- SQLite 数据存储
- 无斜杠命令兼容
- NapCat 接入
- 签到 / 积分系统
- 高级群管插件 v2

## 六、关键端口

- `9000`：qqbot-framework
- `3000`：NapCat OneBot HTTP API
- `6099`：NapCat WebUI

## 七、部署文档

建议优先阅读以下文档：

### 项目总览

- `README.md`

### 部署文档

- `docs/DEPLOY_GUIDE.md`
- `deploy/NAPCAT_DEPLOY.md`
- `deploy/QQ_SCAN_LOGIN.md`

### 插件开发文档

- `docs/PLUGIN_GUIDE.md`

### 发布说明

- `docs/RELEASE_NOTES.md`

## 八、部署最短路径

### 1. 解压

```bash
mkdir -p /opt/qqbot-framework
cd /opt/qqbot-framework
tar -xzf qqbot-framework-release.tar.gz
```

### 2. 配置

```bash
cp .env.example .env
```

至少修改：

```env
ONEBOT_API_BASE=http://127.0.0.1:3000
QQBOT_OWNER_IDS=你的QQ号
```

### 3. 启动框架

```bash
chmod +x run.sh
./run.sh
```

### 4. 部署 NapCat

参考：

- `deploy/NAPCAT_DEPLOY.md`

### 5. 测试命令

部署完成后，可在 QQ 中测试：

- `ping`
- `help`
- `签到`
- `签到状态`
- `积分`
- `群管帮助`
- `插件列表`

## 九、插件编写规范位置

插件规范与开发说明见：

```text
docs/PLUGIN_GUIDE.md
```

其中包含：

- 插件类型
- `MessageContext` 用法
- `ctx.reply()` 使用方式
- OneBot API 能力
- 数据持久化建议
- 权限控制建议
- 最小插件示例
- 插件安装与管理方式

## 十、迁移注意事项

如果迁移到新服务器，建议保留或迁移：

- `.env`
- `data/`
- `user_plugins/`
- `napcat/config/`
- `ntqq/`

注意：

- 登录态迁移后不一定仍然有效
- 若失效，重新扫码属于正常现象

## 十一、已知限制

当前未统一封装：

- JSON 卡片消息发送
- XML 卡片消息发送
- 图片/文件/语音等完整消息段发送接口
- 更完整的 notice/request 事件体系

因此当前最稳定的能力仍然是：

- 文本消息
- OneBot 群管理接口
- 插件式业务逻辑

## 十二、重新打包

如需重新生成发布包：

```bash
./scripts/package_release.sh
```

## 十三、结论

这份交付物已经不是演示骨架，而是一套可以直接落地的 QQ 机器人框架。

它已经适合：

- 自己部署
- 发给别人部署
- 在此基础上继续做插件开发
- 继续扩展更高级消息能力

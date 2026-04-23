# QQ Bot Framework

一个可扩展的 QQ 机器人框架，基于 **Python + FastAPI + OneBot v11**。

当前项目已经实际打通：

- `NapCat`
- `OneBot HTTP API`
- `HTTP 事件上报`

因此它不是纯骨架，而是一套可以实际部署的 QQ 机器人框架。

## 1. 项目定位

这套框架负责：

- 接收 OneBot 事件
- 路由消息到插件
- 执行业务逻辑
- 调用 OneBot API 回消息
- 提供签到、积分、群管、插件系统等能力

QQ 登录本身不由框架实现，而是交给外部 QQ 适配器（当前推荐 NapCat）。

## 2. 现在已经具备

- OneBot v11 事件接收
- HTTP API 回消息适配层
- 插件自动发现与自动加载
- 支持第三方插件安装
- 插件元信息（名称 / 版本 / 作者 / 描述 / 依赖）
- 插件启用 / 禁用管理
- URL / 市场安装插件
- 插件升级 / 卸载
- 主人权限控制
- 聊天内插件管理命令
- 命令插件 / 关键词插件 / 正则插件
- SQLite 本地存储
- 日志初始化
- `.env` 配置加载
- 一键启动脚本 `run.sh`
- Docker / docker-compose 模板
- systemd 服务文件
- 内置签到 / 积分
- 高级群管插件 v2
- 命令同时支持带 `/` 和不带 `/`

## 3. 目录结构

```text
qqbot-framework/
├── app/
├── data/
├── deploy/
├── docs/
├── logs/
├── napcat/
├── ntqq/
├── scripts/
├── user_plugins/
├── .env.example
├── DEPLOY_FINAL.md
├── Dockerfile
├── README.md
├── install_plugin.py
├── requirements.txt
└── run.sh
```

## 4. 环境要求

- Python 3.10+
- 一个可用的 OneBot v11 实现（推荐 `NapCat`）
- 推荐安装 Docker（用于 NapCat）

## 5. 快速开始

### 方式一：交互式一键安装（推荐）

```bash
cd qqbot-framework
chmod +x deploy/install.sh
./deploy/install.sh
```

脚本会交互式帮你：

- 检测系统环境、包管理器、Python、docker、systemd、curl/wget
- 当前一键安装器仅支持 Ubuntu / Debian 系统
- 尝试自动安装缺失依赖
- 强制检测 Python 3.10+，并优先选择 `python3.11` / `python3.10` / `python3`，同时兼容 `/usr/local/bin/python3.10` 这类手动编译安装路径
- 自动尝试安装 Python 相关依赖，并在需要时自动升级 `pip / setuptools / wheel`
- 检查端口占用
- 询问主人 QQ
- 询问端口配置
- 自动生成 `.env`
- 自动生成 systemd 服务文件
- 可选生成 NapCat 配置
- 可选直接启动框架和 NapCat
- 安装后自动做健康检查
- 输出扫码登录 / WebUI 链接登录指引
- 安装完成后进入一轮简短交互，可直接查看健康状态、NapCat 状态、最近日志、控制面板信息、systemd 服务状态，还可导出最新二维码到本机文件、测试给主人发送私聊消息
- 安装完成摘要会自动打印控制面板 / NapCat WebUI 的本机地址与局域网地址，并尝试识别当前登录流程是“二维码登录”还是“验证码验证”
- 当默认 pip 源过旧或镜像未同步时，自动回退到官方 PyPI 源重试

说明：当前安装器**不支持 QQ 明文密码自动登录**，推荐使用扫码登录或 WebUI/链接登录。

### 方式二：GitHub 链接一键安装（适合服务器直接执行）

可以直接在服务器上执行：

```bash
curl -fsSL https://raw.githubusercontent.com/3026591236/qqbot-framework/main/deploy/bootstrap-install.sh | \
  REPO_OWNER=3026591236 REPO_NAME=qqbot-framework REPO_REF=main APP_DIR=/opt/qqbot-framework sh
```

这个 bootstrap 脚本会：

- 从 GitHub 下载整个仓库源码压缩包
- 自动解压
- 自动执行 `deploy/install.sh`
- 然后进入交互式安装流程

当前安装器已经兼容 `curl | sh` 场景，会优先从 `/dev/tty` 读取交互输入。

### 方式三：Git 工作区一键安装（推荐给需要自动更新检测的人）

如果你希望：

- 保留 `.git`
- 支持更完整的更新检测
- 后续可以直接 `git pull`

可以直接在服务器上执行：

```bash
curl -fsSL https://raw.githubusercontent.com/3026591236/qqbot-framework/main/deploy/bootstrap-git-install.sh | \
  REPO_OWNER=3026591236 REPO_NAME=qqbot-framework REPO_REF=main APP_DIR=/opt/qqbot-framework sh
```

这个脚本会：

- 直接 `git clone` 仓库到目标目录
- 保留 `.git` 工作区
- 自动调用 `deploy/install.sh`
- 后续更适合使用更新检测、自动提醒、`git pull` 更新

### 方式四：手动启动

```bash
cd qqbot-framework
cp .env.example .env
chmod +x run.sh
./run.sh
```

默认监听：

```text
http://0.0.0.0:9000
```

健康检查：

```bash
curl http://127.0.0.1:9000/healthz
```

## 6. 关键环境变量

`.env.example` 中常用配置：

```env
QQBOT_APP_NAME=QQ Bot Framework
QQBOT_HOST=0.0.0.0
QQBOT_PORT=9000
QQBOT_DEBUG=false
QQBOT_LOG_LEVEL=INFO
QQBOT_COMMAND_PREFIX=/
ONEBOT_API_BASE=http://127.0.0.1:3000
QQBOT_DATA_DIR=./data
QQBOT_SQLITE_PATH=./data/qqbot.sqlite3
QQBOT_OWNER_IDS=
QQBOT_MARKET_URL=
```

至少建议设置：

```env
ONEBOT_API_BASE=http://127.0.0.1:3000
QQBOT_OWNER_IDS=你的QQ号
```

## 7. QQ 接入方式

### 推荐：NapCat

推荐阅读：

- `deploy/NAPCAT_DEPLOY.md`
- `docs/DEPLOY_GUIDE.md`
- `docs/PANEL_DEPLOY_GUIDE.md`

当前推荐实际对接关系：

- NapCat HTTP API：`http://127.0.0.1:3000`
- 框架服务：`http://127.0.0.1:9000`
- NapCat 上报：`http://host.docker.internal:9000/onebot/event`

## 8. Web 控制面板

当前项目已内置一个 Web 控制面板，默认挂载在主服务下：

```text
http://127.0.0.1:9000/panel
```

面板当前支持：

- 登录认证
- 状态总览
- NapCat / OneBot 状态查看
- 登录二维码查看
- 全局 / 按群卡片模式管理
- 群自动撤回管理
- 运行日志查看

部署与使用说明请看：

- `docs/PANEL_DEPLOY_GUIDE.md`

## 9. AI 中转站使用教程

AI 插件支持使用 OpenAI 兼容接口的中转站，并且可以直接在 QQ 私聊中完成配置，不需要手动改 `.env`。

推荐使用流程：

### 第一步：配置中转站地址和 Key

私聊机器人主人账号发送：

```text
配置AI中转站 https://你的中转站地址/v1 sk-xxxx
```

示例：

```text
配置AI中转站 https://www.63u.cn/v1 sk-xxxx
```

### 第二步：获取模型列表

```text
AI模型列表
```

机器人会从：

```text
GET /v1/models
```

拉取模型，并按编号返回。

### 第三步：按序号选择模型

```text
选择AI模型 1
```

如果你已经知道具体模型名，也可以直接：

```text
切换AI模型 gpt-4o-mini
```

### 第四步：开始对话

```text
AI 你好
问AI 用一句话介绍你自己
```

### AI 相关命令总览

- `AI帮助`
- `AI状态`
- `AI 你的问题`
- `问AI 你的问题`
- `配置AI中转站 地址 Key`
- `AI模型列表`
- `选择AI模型 序号`
- `切换AI模型 模型名`

### 说明

- `配置AI中转站`、`AI模型列表`、`选择AI模型` 建议在**私聊**中使用
- 配置命令默认要求是**主人账号**
- 如果中转站地址里带有 `/v1`，现在也可以正常识别，不会再被未知命令提示插件误拦截

## 9. 内置命令示例

### 通用

- `ping`
- `help`
- `echo 你好`

### 签到系统

- `签到`
- `签到状态`
- `补签`
- `签到排行`
- `积分`

### 插件管理

- `插件列表`
- `启用插件 名称`
- `禁用插件 名称`
- `插件市场`

### 群管

- `群管帮助`
- `群管状态`
- `禁言 @某人 10m`
- `警告 @某人 原因`
- `添加违禁词 词语`

## 10. 插件开发

插件系统支持：

- `CommandPlugin`
- `KeywordPlugin`
- `RegexPlugin`

详细规范请看：

- `docs/PLUGIN_GUIDE.md`
- `docs/CDK_REWARD_QUICKSTART.md`（发卡奖励插件快速说明）

## 11. 插件安装与管理

### 命令行

```bash
python3 install_plugin.py install /path/to/plugin.py
python3 install_plugin.py install market:plugin_name
python3 install_plugin.py upgrade plugin_name
python3 install_plugin.py uninstall plugin_name
python3 install_plugin.py enable plugin_name
python3 install_plugin.py disable plugin_name
python3 install_plugin.py list
python3 install_plugin.py market
```

### 聊天内主人命令

- `插件列表`
- `启用插件 名称`
- `禁用插件 名称`
- `插件市场`

## 12. 文档导航

建议阅读顺序：

1. `README.md`
2. `DEPLOY_FINAL.md`
3. `docs/DEPLOY_GUIDE.md`
4. `deploy/NAPCAT_DEPLOY.md`
5. `docs/PLUGIN_GUIDE.md`
6. `docs/RELEASE_NOTES.md`

## 13. 发布与打包

重新生成发布包：

```bash
./scripts/package_release.sh
```

生成文件：

```text
qqbot-framework-release.tar.gz
```

## 14. 安全提醒

不要把这些内容直接打包公开分发：

- `.env`
- `data/`
- `ntqq/`
- `napcat/cache/`
- 运行日志
- 本机登录态

## 15. 当前限制

当前框架稳定支持：

- 文本消息
- OneBot HTTP API 调用
- 插件系统
- 群管理接口

当前还未统一封装：

- JSON/XML 卡片消息发送
- 图片/语音/文件等完整消息段构造器
- 更完整的高级事件体系

如果你后续要做这些能力，建议扩展：

- `app/adapters/onebot.py`
- `app/core/context.py`

## 16. License

本项目默认按 `MIT` License 开源，见：

- `LICENSE`
- `SECURITY.md`

## 17. 最终结论

这套框架已经具备：

- 可部署
- 可迁移
- 可扩展
- 可插件化
- 可扫码登录接入 QQ
- 可长期继续开发

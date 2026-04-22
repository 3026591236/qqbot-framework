# QQ Bot Framework 面板部署教程

本文档说明如何为 `qqbot-framework` 启用和使用内置 Web 控制面板。

当前面板已支持：

- 面板登录认证
- 框架 / OneBot / NapCat 状态查看
- NapCat 登录二维码查看
- 全局卡片模式切换
- 按群卡片模式管理
- 群自动撤回管理
- 运行日志查看

---

## 1. 面板访问地址

默认情况下，面板挂在主服务下：

```text
http://127.0.0.1:9000/panel
```

如果你的服务监听在公网，例如：

```text
http://你的服务器IP:9000/panel
```

例如本次实际部署环境中：

```text
http://38.12.5.26:9000/panel
```

---

## 2. 启用面板口令

面板默认依赖环境变量 `QQBOT_PANEL_PASSWORD` 进行登录认证。

请在 `.env` 中添加：

```env
QQBOT_PANEL_PASSWORD=你的面板口令
```

例如：

```env
QQBOT_PANEL_PASSWORD=ChangeMeToAStrongPassword
```

说明：

- **不要**把这个口令提交到 GitHub
- `.env` 属于本地运行配置，应保留在服务器本地
- 建议使用足够长的随机口令

---

## 3. 一键安装器支持

当前 `deploy/install.sh` 已支持：

- 安装过程中交互式设置 `QQBOT_PANEL_PASSWORD`
- 安装完成后直接显示：
  - 本机面板地址
  - 外部面板地址
  - 面板口令

也就是说，如果你通过一键安装器部署，安装结束时就能直接看到面板入口，不需要自己再翻配置文件。

## 4. 启动方式

面板不需要单独启动，它直接挂载在 `qqbot-framework` 主 FastAPI 服务中。

只要主服务启动，面板就会自动可用。

例如：

```bash
cd qqbot-framework
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9000
```

或者使用你已有的 systemd / run.sh / nohup 启动方式。

---

## 5. 当前面板依赖的服务关系

典型部署关系如下：

- `qqbot-framework`：`http://127.0.0.1:9000`
- NapCat HTTP API：`http://127.0.0.1:3000`
- NapCat WebUI：`http://127.0.0.1:6099`

面板内部会：

- 调用 `ONEBOT_API_BASE` 获取 OneBot 状态
- 读取 `napcat/config/webui.json` 中的 token
- 登录 NapCat WebUI
- 获取 QQ 登录信息与二维码

因此请确保以下文件存在且配置正确：

```text
napcat/config/webui.json
```

以及 `.env` 中至少有：

```env
ONEBOT_API_BASE=http://127.0.0.1:3000
QQBOT_OWNER_IDS=你的QQ号
QQBOT_PANEL_PASSWORD=你的面板口令
```

---

## 6. 面板当前可用功能

### 5.1 总览状态

可查看：

- 框架健康状态
- OneBot 在线状态
- NapCat 在线状态
- 机器人 QQ 号
- 机器人昵称
- 当前全局卡片模式

---

### 5.2 全局卡片模式

可以直接在面板里切换：

- `text`
- `image`

对应的是全局默认模式。

---

### 5.3 按群卡片模式

可以输入群号查看与修改：

- 当前群是否有独立卡片模式
- 实际生效模式
- 是否回退到全局默认

---

### 5.4 群自动撤回

可以输入群号查看与设置：

- 是否开启自动撤回
- 自动撤回秒数

---

### 5.5 NapCat 登录二维码

可以在面板中：

- 导出当前 NapCat 登录二维码
- 直接显示二维码图片

当前二维码导出文件默认保存到：

```text
qqbot-framework/data/panel/qrcode.png
```

---

### 5.6 运行日志

当前面板支持查看日志 tail。

当前实现默认读取：

```text
/tmp/qqbot-framework-web.log
```

如果你使用 systemd、supervisor 或其他日志方案，需要按你的实际日志路径调整代码。

---

## 7. 公网访问注意事项

当前面板即使已经有登录口令，也仍然建议：

### 方案 A：仅内网 / 本机访问（最安全）

例如仅在服务器本机打开：

```text
http://127.0.0.1:9000/panel
```

### 方案 B：公网临时使用

可以直接访问：

```text
http://服务器IP:9000/panel
```

但请注意：

- 这通常是 **HTTP 明文**
- 口令与 cookie 不如 HTTPS 安全
- 不建议长期裸奔暴露在公网

### 方案 C：推荐长期方案

给面板前面加一层反向代理并启用 HTTPS，例如：

- Nginx
- Caddy
- Cloudflare Tunnel
- Tailscale Serve / Funnel

如果你有域名，推荐优先使用：

- `https://panel.your-domain.com/panel`

---

## 8. 常见问题

### Q1：访问 `/panel` 只有登录页，没有面板内容？

这是正常的，说明登录认证已生效。

请确认：

- `.env` 中已设置 `QQBOT_PANEL_PASSWORD`
- 输入的口令正确
- 主服务已重启加载新配置

---

### Q2：面板里 NapCat 状态显示异常？

请检查：

- `napcat/config/webui.json` 是否存在
- NapCat WebUI 是否启动（默认 `6099`）
- OneBot / NapCat 是否在线

可手动验证：

```bash
curl -s http://127.0.0.1:3000/get_status
curl -s http://127.0.0.1:9000/healthz
```

---

### Q3：二维码不显示？

请检查：

- NapCat 容器名是否仍然叫 `napcat`
- 容器内二维码路径是否仍然是：

```text
/app/napcat/cache/qrcode.png
```

如果部署方式不同，需要同步调整面板里的二维码导出逻辑。

---

### Q4：改了 `.env` 之后面板没变化？

因为 `.env` 改动后需要重启主服务。

例如：

```bash
pkill -f 'uvicorn app.main:app'
cd qqbot-framework
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9000 > /tmp/qqbot-framework-web.log 2>&1 &
```

---

## 9. 后续可扩展方向

当前面板只是第一版，后续很适合继续加入：

- CDK 奖励管理页
- NapCat 登录操作页
- 测试发消息页
- 群列表 / 成员信息页
- 插件开关页
- 更完善的日志与告警页

---

## 10. 相关文件

当前面板相关核心文件：

```text
app/web/panel.py
app/main.py
app/config.py
.env
```

如果你准备二次开发，建议优先从：

```text
app/web/panel.py
```

开始看。

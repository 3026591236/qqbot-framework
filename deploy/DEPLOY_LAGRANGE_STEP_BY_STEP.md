# Lagrange 一键部署落地步骤

## 1. 解压项目

```bash
tar -xzf qqbot-framework-release.tar.gz -C /opt/qqbot-framework
cd /opt/qqbot-framework
```

## 2. 初始化目录和配置

```bash
chmod +x deploy/bootstrap-lagrange.sh
./deploy/bootstrap-lagrange.sh /opt
```

如果你是直接在项目目录运行，也可以：

```bash
./deploy/bootstrap-lagrange.sh
```

## 3. 修改 `.env`

重点检查：

```env
ONEBOT_API_BASE=http://lagrange:5700
QQBOT_OWNER_IDS=你的QQ号
```

## 4. 修改 `lagrange/data/appsettings.json`

重点检查：

- HTTP API 端口是否为 5700
- 反向 HTTP 上报地址是否为 `http://qqbot-framework:9000/onebot/event`
- 是否开启二维码登录
- 是否持久化登录状态

## 5. 启动

```bash
docker-compose -f deploy/docker-compose.lagrange.yml up -d --build
```

## 6. 查看日志

```bash
docker logs -f lagrange-onebot
```

## 7. 手机 QQ 扫码

第一次启动后，按 Lagrange 输出的二维码/登录提示完成登录。

## 8. 验证框架

```bash
chmod +x deploy/check-lagrange.sh
./deploy/check-lagrange.sh
```

然后给机器人发送：

```text
/help
```

## 9. 常见问题

### 没有二维码
- 看 Lagrange 日志
- 检查配置字段是否和你实际镜像版本一致
- 检查容器是否成功启动

### 扫码后没消息
- 检查 `ONEBOT_API_BASE`
- 检查 `qqbot-framework:9000/onebot/event` 是否配置正确
- 检查 5700 和 9000 端口映射

### 重启后需要重新扫码
- 检查 `./lagrange/data` 是否已正确挂载并持久化
- 如果你机器上只有老版 Compose，请统一使用 `docker-compose` 而不是 `docker compose`

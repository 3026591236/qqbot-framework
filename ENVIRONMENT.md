# 环境准备说明

这个项目支持 **交互式一键安装**。

## 推荐安装方式

进入项目目录后直接运行：

```bash
chmod +x deploy/install.sh
./deploy/install.sh
```

脚本会自动：

- 检测 Python / docker / systemd / curl
- 询问主人 QQ
- 询问框架端口 / OneBot 端口 / WebUI 端口
- 自动生成 `.env`
- 自动生成 systemd 服务文件
- 可选生成 NapCat 配置
- 可选启动 qqbot-framework
- 可选启动 NapCat

## 你仍然可以手动部署

如果你不想使用一键脚本，也可以：

```bash
cp .env.example .env
chmod +x run.sh
./run.sh
```

## 文档入口

- 总说明：`README.md`
- 部署说明：`docs/DEPLOY_GUIDE.md`
- NapCat 接入：`deploy/NAPCAT_DEPLOY.md`
- 插件编写规范：`docs/PLUGIN_GUIDE.md`

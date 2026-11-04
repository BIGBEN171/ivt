# 腾讯云本地前端部署

2026-11-04 起，HTTPS 8082 直接提供服务器本地文件，不再代理 GitHub Pages。本文描述前端的当前状态，替代 TENCENT.md 中原有的前端反向代理说明。

- 页面：`https://62.234.95.210:8082/`
- 当前版本：`/var/www/clarity-frontend/current`，指向 `releases/<SHA>`。
- 公网 `/version.json` 返回当前前端提交 SHA。
- Nginx 配置：`/etc/nginx/conf.d/clarity-public.conf`。
- Python 继续只监听 `127.0.0.1:8010`。公网 API、文档和照片路径返回 404。

## 自动更新

推送到 main 后，frontend-ci.yml 独立运行前端测试与构建。服务器 clarity-frontend-deploy.timer 约每五分钟检查一次，只有精确提交的 CI 成功才下载源码、安装锁定依赖、重新测试并构建。

控制脚本 `/usr/local/lib/clarity-deploy/frontend_deployer.py` 由 root 安装；运行用户是 ubuntu。仅 dist 构建产物对外发布，源码和 node_modules 位于私有临时构建目录。原子切换 current 后，通过本机 HTTPS 检查版本；检查失败则切回旧版本。首次 bootstrap 在安装静态 Nginx 配置后单独验收。

静态资源 URL 包含版本 SHA，保留旧版本以支持已打开的页面及人工回退。目前不自动清理历史版本；可用空间不足 2 GiB 时拒绝新构建。更新前后端互不要求重启对方。原 GitHub Pages 部署继续独立存在，但腾讯云无需等待 Pages 发布。

系统脚本、Nginx 和 systemd 配置不随应用版本自动覆盖，后续修改这些部署文件仍需要人工安装。现阶段前端只本地拍照保存，未接通后端上传。

```bash
# Inspect the scheduled frontend checks and the latest execution logs.
systemctl list-timers clarity-frontend-deploy.timer --no-pager
journalctl -u clarity-frontend-deploy.service -n 50 --no-pager
# Inspect which complete release Nginx is serving.
readlink -f /var/www/clarity-frontend/current
```

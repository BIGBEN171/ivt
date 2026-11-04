# 腾讯云部署记录

> 2026-11-04 更新：前端已迁移为腾讯云本地静态托管，下面的前端反向代理段落是历史记录。当前前端路径、独立自动部署和版本回退说明见 [FRONTEND.md](FRONTEND.md)。后端内部访问和自动部署流程仍有效。

目标：已有的北京轻量应用服务器，Ubuntu 24.04。最初只部署内部接口；2026-11-03 按要求新增独立的公网 HTTP 测试入口。

## 公网前端入口（当前状态）

- 前端页面：`https://62.234.95.210:8082/`；原 HTTP 地址自动跳转。
- 请求路径：公网 TCP 8082 → Nginx → GitHub Pages 已发布的前端。
- 这是前端反向代理，不是服务器本地静态副本；依赖 GitHub Pages 可用性，页面随现有 Pages 自动发布更新。
- Python 后端保持 `127.0.0.1:8010`，8082 不再转发任何后端请求。已验证 `/api/v1/health`、`/docs`、`/openapi.json` 和照片地址在公网均返回 404。
- 配置源文件：`backend/deploy/clarity-public.conf`；服务器安装路径：`/etc/nginx/conf.d/clarity-public.conf`。配置变更需手动安装并执行 `nginx -t` 和重载。
- 防火墙的 TCP 8082 规则保留；原备注 `Clarity Capture HTTP test API` 是历史名称。
- HTTPS 使用受信任的 IP 证书，续期任务和端口用途见 [HTTPS 运维说明](HTTPS.md)。摄像头和文件夹仍需要用户在浏览器内授权；后端自动部署继续使用内部健康检查。

关闭整个公网前端入口时，可在云防火墙删除 TCP 8082 规则，或停止该 Nginx 监听：

```bash
# Disable only this frontend gateway; keep the internal API and its deployment timer.
sudo mv /etc/nginx/conf.d/clarity-public.conf /etc/nginx/conf.d/clarity-public.conf.disabled
# Check the complete configuration before reloading existing workers.
sudo nginx -t && sudo systemctl reload nginx
```

## 路径与进程

- 当前版本入口：`/opt/clarity-capture-current`（root 管理的符号链接）
- 新版本目录：`/home/ubuntu/clarity-releases/<完整提交 SHA>`，每版独立 `.venv`
- 初始版本保留在 `/home/ubuntu/clarity-capture`，可供回退
- 上传数据：`/home/ubuntu/clarity-capture-data`（与源码分开）
- 版本记录：程序目录中的 `DEPLOYED_COMMIT`
- systemd 服务：`clarity-capture.service`
- Python 监听地址：`127.0.0.1:8010`；仅限服务器内部访问

已于 2026-11-03 完成内部部署。服务器 Python 3.12.3 下 9 项测试通过；本地和 GitHub CI 使用 Python 3.13。

部署版本：`0ccf4fed9a5e729babbfff49ab3eeb48fc880e94`。

实际 HTTP 验收已通过：健康检查、生成测试 PNG 上传、重复上传去重、元数据读取、原始图片字节比对。重启本服务后元数据仍可读取，服务已设置开机启动，监听地址确认为 `127.0.0.1:8010`。

数据目录中保留一张 4×3 像素的绿色测试图片，ID 为 `246684b7-7188-4b70-8e77-3117df492b83`；没有使用真实患者照片。已有其他网站和防火墙规则未改动。

## 日常检查（在腾讯云终端执行）

```bash
# Inspect service state without changing it.
systemctl status clarity-capture --no-pager

# Check the local HTTP endpoint.
curl --fail http://127.0.0.1:8010/api/v1/health

# Read recent application logs.
sudo journalctl -u clarity-capture -n 50 --no-pager
```

## 手动维护

```bash
# Restart only this API, leaving existing applications untouched.
sudo systemctl restart clarity-capture

# Stop the API if it is no longer needed.
sudo systemctl stop clarity-capture
```

重启程序不会删除独立数据目录。服务器磁盘上的数据仍需备份；它不是腾讯云 COS，也没有跨服务器复制。

## GitHub 推送后的自动更新

服务器使用 `clarity-deploy.timer`，开机约 2 分钟后首次检查，之后每次检查结束约 5 分钟再检查（附加最多 20 秒随机延迟）。这不是即时 webhook；CI 通过后通常还需等待一个轮询周期及安装测试时间。

1. 读取公开仓库 BIGBEN171/ivt 的 main 最新提交。
2. 只接受同一 SHA、main、push 事件的 `backend-ci.yml` 最新运行，且必须完成并 success。
3. 下载固定 SHA 的官方源码包，以 ubuntu 身份在独立版本目录创建虚拟环境、安装依赖、运行后端全部测试。
4. 再次确认 main 和 CI 状态；若期间又有新提交，不发布旧候选版本。
5. 记录旧版本路径，切换符号链接，重启固定的 clarity-capture 服务，检查内部健康接口。
6. 健康检查失败则回退旧版本；自动部署进程在切换期间被中断时，下次检查先恢复旧版本。

下载、CI 或安装测试失败不会重启当前服务。启动后失败的 SHA 被记录，避免每 5 分钟重复切换；修复后推送新的提交即可重试。没有配置云端数据库迁移回滚。

状态记录在 `/var/lib/clarity-deploy/state.json`。成功版本保留以便回退，不自动清理；剩余磁盘不足 2 GiB 时停止构建新版本，需要人工清理确认不再使用的版本目录。

```bash
# Inspect the next poll and recent deployment results.
systemctl list-timers clarity-deploy.timer --no-pager
sudo journalctl -u clarity-deploy.service -n 80 --no-pager
sudo cat /var/lib/clarity-deploy/state.json

# Request an immediate check; this still requires successful GitHub CI.
sudo systemctl start clarity-deploy.service

# Pause future polling without stopping the current API or an ongoing deploy.
sudo systemctl disable --now clarity-deploy.timer
```

无需 GitHub Secrets、服务器 SSH 密钥、Webhook 或额外防火墙端口。仅适用于当前公开仓库；改为私有仓库后需重新设计认证。匿名 GitHub API 有速率限制；通常无变化时约 12 次请求/小时。临时网络故障会记录日志并在后续轮询重试。

特权控制脚本安装在 `/usr/local/lib/clarity-deploy/deployer.py`，归 root 所有；代码下载、依赖安装与 pytest 都使用 ubuntu 身份执行。控制脚本和 systemd 配置**不会随仓库自动替换**，修改这些文件后需要人工审查并更新安装副本；普通业务后端更新会自动部署。

首次安装时创建版本入口、部署状态和 timer，并把现有 API 服务路径切换到符号链接。整个流程只管理此项目，不更改其他服务。

服务器到 GitHub 的 Git 连接在检查时超时，但官方 codeload 下载入口可访问。因此首版按明确的提交 SHA 下载源码包，不使用不确定的最新分支内容。

以后更新应先在独立版本目录安装与测试，通过后切换服务；保留上一版供回滚，不能覆盖或清空照片目录。

## 公网接入前

需要确定 HTTPS 地址和认证方案，再添加反向代理。不要把当前无认证的 8010 端口直接放通到公网。前端仍未添加上传调用，公开网页不会因这次内部部署而自动上传照片。

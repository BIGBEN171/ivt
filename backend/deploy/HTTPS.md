# 腾讯云前端 HTTPS 运维

前端地址：`https://62.234.95.210:8082/`。Nginx 直接提供腾讯云本地构建文件，不转发 GitHub Pages 或 Python API。前端更新由独立的 CI 和服务器定时任务完成，详见 FRONTEND.md。GitHub 或 npm 暂时不可用会影响新版本构建，但不影响已部署页面的访问。

## 证书与端口

- 使用 Let's Encrypt 的 `shortlived` IP 证书，无需域名，证书有效期约 6 天。
- 8082：Nginx HTTPS 前端；同端口的普通 HTTP 请求跳转到 HTTPS。
- 443：仅在申请或续期时由 Lego 临时监听，用于 TLS-ALPN-01 验证。不要把该端口分配给其他程序，否则续期会失败。
- 80：原有程序继续使用，本项目不改动。
- 8010：Python 只监听 `127.0.0.1`，保持内部访问。

## 文件与定时任务

- `/usr/local/bin/clarity-lego`：官方 Lego v5.6.0 Linux amd64 二进制。
- 官方压缩包 SHA256：`f02fc11b6f56b97e387fa7caa0268f86f5a336953b22458e6430e4651fea439a`。
- `/var/lib/clarity-acme`：正式证书和 ACME 账户，root 专用。私钥不能加入 GitHub。
- `/var/lib/clarity-acme-staging`：独立测试证书和账户；不会被前端使用。
- `/etc/nginx/conf.d/clarity-public.conf`：前端路由和 TLS 配置。
- `/usr/local/lib/clarity-deploy/reload-frontend-tls.sh`：证书更新成功后验证配置并重载 Nginx。
- `clarity-tls-renew.timer`：每 6 小时检查一次，附加最多 10 分钟随机延迟；关机错过的任务开机后补做。
- `clarity-tls-renew.service`：Lego 根据证书有效期与 CA 续期信息决定是否续期；不需要每次都签发新证书。

源配置位于本目录，均带英文注释。配置文件需人工安装到上述系统路径，不会被后端 GitHub 自动部署替换。无需配置 DNS 或云账户密钥。

## 检查与维护

```bash
# Check the automatic renewal schedule and the last run result.
systemctl list-timers clarity-tls-renew.timer --no-pager
systemctl status clarity-tls-renew.service --no-pager
sudo journalctl -u clarity-tls-renew.service -n 50 --no-pager

# Inspect public certificate dates without printing its private key.
sudo openssl x509 -in /var/lib/clarity-acme/certificates/62.234.95.210.crt -noout -dates -issuer -ext subjectAltName

# Check renewal immediately; this does not force an unnecessary issuance.
sudo systemctl start clarity-tls-renew.service

# Confirm the API is still reachable only through its internal listener.
curl --fail http://127.0.0.1:8010/api/v1/health
ss -ltn 'sport = :8010'
```

若公网 IP 改变，必须修改证书目标和 Nginx 的证书路径、跳转地址，并重新申请证书。保持 TCP 443 云防火墙规则可达。若续期任务失败，应及时检查日志；短期证书不能长期搁置。HTTPS 只解决浏览器安全上下文和传输加密，不意味着已启用患者身份验证或云上传。

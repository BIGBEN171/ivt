# Python 后端 · 本地开发版

这是拍照项目的独立 FastAPI 后端，为以后的云端传输准备接口。当前前端没有调用它，原有拍照和本机保存行为保持不变。所有 Python 代码和测试均带英文注释。

腾讯云已部署仅服务器内部可访问的实例，并配置检查 GitHub CI 后更新的定时器；详见 [部署与维护说明](deploy/TENCENT.md)。下列启动命令仍用于本地开发。

## 启动（Windows PowerShell）

在项目根目录 `F:\网页` 执行。建议 Python 3.13（本次验证版本）；虚拟环境隔离于前端依赖。

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

健康检查：http://127.0.0.1:8000/api/v1/health

交互式接口文档：http://127.0.0.1:8000/docs （文档 UI 默认需要联网加载资源）

停止服务：Ctrl+C。服务只监听本机，不向局域网或公网开放。

## 项目结构

```text
backend/
  main.py          HTTP 路由、PNG 校验、状态码、跨域配置
  config.py        存储位置、大小与像素限制、允许的前端来源
  models.py        照片元数据与上传回执的数据约定
  storage.py       本地存储实现、原子提交、同一照片的重复上传处理
  tests/test_api.py 接口与存储测试，使用生成图片和临时目录
  requirements.txt 已验证并锁定的 Python 依赖（包含测试工具）
  data/            运行时产生；照片和元数据，不提交到 Git
```

关系：未来前端上传模块 → HTTP → `main.py` → `storage.py`。`models.py` 规定响应结构，`config.py` 提供配置。后端不导入前端文件，不控制摄像头。

## 接口约定

| 方法与路径 | 用途 |
| --- | --- |
| GET /api/v1/health | 服务存活检查 |
| POST /api/v1/photos | 上传一张 PNG 与拍摄元数据 |
| GET /api/v1/photos/{photo_id} | 查询照片元数据 |
| GET /api/v1/photos/{photo_id}/image | 读取原始 PNG |

上传使用 `multipart/form-data`，包含三个必填字段：

| 请求字段 | 对应现有前端 Photo 对象 | 说明 |
| --- | --- | --- |
| photo_id | photo.id | UUID；失败重试必须复用同一 ID |
| captured_at | photo.capturedAt | 带时区的 ISO 时间，例如 2026-11-03T00:00:00Z |
| file | photo.blob | PNG 文件；服务器忽略客户端文件名 |

后端根据图片实际内容校验格式、尺寸并计算 SHA-256。默认最大 20 MiB、2500 万像素；不支持动画 PNG。

首次接收返回 201，结构为 `{ "photo": { ...元数据 }, "duplicate": false }`。相同 ID、内容和拍摄时间再次上传返回 200 和 `duplicate: true`，沿用首次接收时间。相同 ID 对应不同内容或时间返回 409，不覆盖原文件。

其他状态码：404 不存在，413 大小/像素超限，415 格式不支持，422 数据无效，503 写入失败。前端以后只能在收到成功回执后标记“上传成功”，本地保存状态与上传状态应独立。

手动测试（替换文件路径；只用测试图片）：

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/photos -F "photo_id=3d752d9a-e299-4b30-a9bb-bcc1c8c3e904" -F "captured_at=2026-11-03T00:00:00Z" -F "file=@C:/test/sample.png;type=image/png"
```

## 数据保存在哪里

默认：`backend/data/<photo_id>/image.png` 和 `metadata.json`。可以在启动前设置 `$env:CAPTURE_DATA_DIR = 'D:\capture-data'` 改变位置。

先在临时目录写入完整图片和元数据，再将整个目录重命名为 UUID，避免普通请求读到半份记录。失败清理临时目录；进程被强行终止时可能留下 `.upload-*` 临时目录，当前没有自动清理或断电持久性保证。

文件保存在**后端运行的电脑**，与前端工作人员选择的文件夹不同。当前未接云端，没有数据库、账号、患者关联或识别服务。

## 测试

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
```

测试涵盖上传读取、重试去重、ID 冲突、无效图片、大小限制、元数据校验、磁盘失败、并发重试和开发跨域。不会读取真实照片。

## 将来上云需要做什么

1. 前端新增上传服务，在本地保存成功后安排上传，设计持久化队列和断网重试。
2. 后端单独部署到能运行 Python 的服务；GitHub Pages 只能继续托管前端。
3. 接入身份认证、照片访问权限、HTTPS，并设置准确的前端跨域来源。CORS 不能替代认证。
4. 将本地存储替换为持久云存储，保留 ID、校验与重试语义；规划备份和保留策略。
5. 在网关限制整个请求体大小及请求速率。当前大小检查发生在 multipart 解析之后，不是网关级流量限制。

这一版没有认证，因此只能在本机或服务器内部使用，不能直接公开用于真实患者照片。Pages 工作流仍只部署前端；腾讯云服务器主动检查后端 CI 并拉取代码，不依赖 Pages 来发布 Python 服务。

接口实现参考：[FastAPI 文件与表单文档](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/)。

# Windows 单机版本

本分支 `codex/local-hospital` 用于医院单台 Windows 电脑，不部署到腾讯云或 GitHub Pages。

## 使用

安装 Python 3.13 和 Node.js 22 后，在项目目录运行：

```powershell
# Optional: choose a writable local data root before launching.
$env:CAPTURE_DATA_DIR = 'D:\HospitalCapture\data'
# Keep the terminal running while using the application.
powershell -ExecutionPolicy Bypass -File .\Start-Local.ps1
```

首次安装依赖需要网络；依赖安装后，本机采集和保存不需要云服务。若没有指定目录，启动脚本使用 `%LOCALAPPDATA%\ClarityCapture\data`。打开 `http://127.0.0.1:8000`，使用新版 Chrome 或 Edge。

开始页点击 **Start** → 允许摄像头 → 画面就绪后倒计时 3 秒 → 自动采集 15 个新视频帧 → 保存整组 → **Next session** 返回开始页。

浏览器按 `requestVideoFrameCallback` 通知采样，跳过相同的 `mediaTime`，不承诺 10ms 间隔或完全不丢帧。相邻照片画面内容可能相同（例如被摄物静止），新帧不等于画面必须变化。15 帧先保留为画布，再编码 PNG 和上传本机，避免每张照片的编码或网络请求阻塞采样。浏览器实际呈现帧可能慢于摄像头输出，验收时应核对数据库记录的相邻 `media_time_ms` 和 `sampled_ms` 差值。

失败保存使用 **Retry save** 重试相同批次；不要刷新或关闭页面，未确认保存的照片还在内存里。切换后台或摄像头停止时，未完成的采集不会被登记为成功批次。

## 结构和数据

- `src/main.jsx`：开始、连接、倒计时、采集、保存、失败重试、完成页面。
- `src/services/burst.js`：按视频新帧采样、记录时间、编码 PNG。
- `src/services/api.js`：整组传给本机 Python，校验保存回执。
- `backend/main.py`：校验 15 张 PNG 和时间序列，提供接口及构建好的前端。
- `backend/batches.py`：SQLite 索引、文件保存与相同批次重试。
- `Start-Local.ps1`：准备依赖、构建网页、启动仅监听本机的 Python 服务。

数据库为数据目录下的 `capture.db`，图片在 `photos/<批次 UUID>/<照片 UUID>.png`。数据库仅记录相对路径，数据目录整体搬迁后可通过环境变量重新指定。表 `batches` 保存完整批次，`batch_photos` 保存照片序号、尺寸、校验值和时间。没有患者身份信息，也未运行识别模型。

浏览器的 `captured_at` 是取图时的系统时钟；`sampled_ms` 是单页面单调时钟；`media_time_ms` 是视频时间轴。它们都不是设备曝光时间。

文件写入与 SQLite 事务不是一个原子操作：代码先落盘再提交索引。中断可能留下未登记的图片文件夹；同一批次重试会验证其清单和图片校验值后补充索引。刷新后浏览器不会自动恢复未保存批次，当前没有自动恢复历史遗留文件夹的界面。备份时先关闭本地服务，再复制完整数据目录（数据库和照片都需要备份）。

本机接口：`POST /api/v1/batches` 保存，`GET /api/v1/batches` 最近 100 组，`GET /api/v1/batches/{id}` 查询，`GET /api/v1/batches/{id}/photos/{photo_id}` 读图。完成页提供本次 15 张缩略图；历史查询界面和识别程序另行设计。旧单张接口暂时保留兼容原有代码，不迁移旧数据。

## 验证

```powershell
# Run deterministic tests without a real camera or patient photos.
npm test
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
npm run build
```

真实摄像头帧率、患者姿态和实际拍摄间隔仍需在目标 Windows 电脑验收。不要将照片、数据库或包含照片的运行日志加入 Git。

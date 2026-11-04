# 前后端连接（2026-11-04）

当前入口是 `https://62.234.95.210:8082/`。浏览器负责摄像头预览和生成 PNG；点击拍照后，`src/services/api.js` 用 multipart POST 请求 `/api/v1/photos`，由 Nginx 转发给 `127.0.0.1:8010` 的 Python 服务。

后端校验图片和元数据，经 LocalPhotoStore 保存后返回回执，前端才显示 Saved to server。照片存储在 `/home/ubuntu/clarity-capture-data/<照片 UUID>/image.png`，同目录 metadata.json 保存时间、大小和摘要。前端现在不再要求选择文件夹，也不再将照片写入访问者本机文件夹。

保存失败时保留内存中的照片，并允许 Retry save。重试使用原 ID、时间和图片内容，后端去重。刷新或关闭页面会丢失未保存的内存照片；此版本没有持久化离线上传队列。

按当前要求不设置身份验证；任何能访问该地址的人都能提交上传请求。只转发照片上传路径，照片读取接口和 API 文档仍限服务器内部。Python 端口本身不对公网开放。Nginx 请求体上限 21 MiB，图片本身上限 20 MiB。

本地开发先运行 Python（8000 端口），再运行 Vite；vite.config.js 将 /api 代理到 Python。GitHub Pages 只能托管静态页面，没有这个同源 API；完整拍照保存功能应使用腾讯云地址。

应用代码推送 main 后由已有前后端任务自动更新；Nginx 系统配置仍须单独安装。新增服务模块和配置均带英文注释。旧 localStorage.js 暂时保留供学习，当前 App 不再调用它。

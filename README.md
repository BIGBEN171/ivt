# 清晰 · 本机拍摄原型

JavaScript + React。当前仅实现本机摄像头预览、拍照、保存至工作人员授权的文件夹；不上传照片，不包含诊断功能。

## 启动

安装 Node.js 后，在项目目录运行：

```sh
npm install
npm run dev
```

用桌面 Chrome 或 Edge 打开终端显示的 localhost 地址。工作人员开启摄像头、允许权限、选择可写文件夹。患者点击“拍照”，页面取得视频的一帧并自动保存 PNG。保存完成才显示成功。生产构建：`npm run build`；预览构建：`npm run preview`。

## 模块与接口

| 文件 | 接口 / 职责 |
| --- | --- |
| src/main.jsx | React 页面、准备状态、拍照与保存顺序、重试、防重复点击 |
| src/services/camera.js | openCamera() → MediaStream；closeCamera(stream)；capturePhoto(video) → Photo |
| src/services/localStorage.js | supportsDirectorySaving()；chooseDirectory() → 目录句柄；savePhoto(directory, photo) → 保存回执 |
| src/services/errors.js | 将设备及权限错误转换为中文提示 |
| src/styles.css | 页面外观与布局 |

Photo 对象包含 id（UUID）、capturedAt（UTC ISO 时间）、blob（PNG 文件）、width、height、filename。拍摄以视频实际尺寸为准；1920×1080 仅为期望值，摄像头可能返回其他尺寸。PNG 避免额外有损编码，但不会提升摄像头本身的画质。画面不镜像、不裁剪、不美化。

数据流：摄像头 → 浏览器内存中的 Photo → 授权文件夹中的 PNG。图片不存入项目目录，不应提交到 GitHub。文件名使用 UTC 时间和完整 UUID；重试同一张照片使用同一个文件名。

## 状态与错误

摄像头：off → starting → ready。拍摄流程：idle → capturing → saving → saved / failed。
仅当摄像头就绪且已选目录时允许拍照。保存期间锁定操作；保存失败保留当前照片，阻止新拍摄覆盖它，支持重新授权目录并重试。当前待保存照片只在内存中，刷新、关闭或浏览器崩溃会丢失；页面提供离开提醒，但不构成持久化保障。成功保存后的图片仍在用户文件夹中。

目录授权仅用于当前页面会话，重新打开页面需要重新选择。使用 localhost 或 HTTPS；不能通过普通局域网 HTTP 地址保证摄像头可用。不使用静默拍摄，工作人员主动开启摄像头；关闭按钮或卸载页面时释放摄像头。

## 后续云端扩展边界（尚未实现）

保持 capturePhoto 和 savePhoto 各自独立。后续增加 uploadPhoto(photo) 模块，在本地保存成功之后安排后台上传；上传失败不改变“本地保存成功”的事实。云端方案确定后需要设计持久化待上传队列、断网重试、以 photo.id 去重、访问认证和独立上传状态。当前没有空壳上传调用，也没有假成功回执。

第一版无患者信息：照片编号不能替代患者身份。后续关联方式需单独确定。GitHub 管理代码、网站托管、云端照片存储是三个不同职责。

## 人工验收

1. 开启摄像头并确认实时预览，拒绝权限时有提示且可重试。
2. 选择目录；取消选择不造成错误或丢失原目录。
3. 拍照，确认文件夹存在可打开的 PNG，尺寸与页面一致。
4. 连续快速点击不生成重复拍摄；正常完成后可以再拍。
5. 撤销文件夹权限后拍摄，确认保存失败保留照片；重新选择目录后重试成功。
6. 关闭摄像头后禁止拍摄；刷新后重新准备；断网时本机拍摄保存仍可用（已加载页面）。

自动测试使用模拟文件句柄验证写入完成才返回成功、失败回传及重试文件名一致；真实硬件和系统文件夹授权仍需人工验收。

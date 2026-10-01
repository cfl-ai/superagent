# SuperAgent 桌面版 / 云端多设备版

统一 **Web 控制台**（`/`），桌面版与云端版共用同一套 UI：

- **桌面版**：本机运行，浏览器访问 `http://localhost:8000`
- **云端版**：部署在服务器，任意设备浏览器访问 `http://<服务器IP>:8000`（多设备共享）

## 桌面版（Windows）

双击 `start-desktop.bat`，自动启动本地服务并打开浏览器。
首次使用需先安装 Python 3.10+，并在 `.env` 填入 `DEEPSEEK_API_KEY`。

## 桌面版（Linux/macOS）

```bash
bash start-desktop.sh
```

## 云端多设备版

服务已部署后，任意设备浏览器打开：
```
http://47.109.30.40:8000
```
在页面右上角填入 **API Key**（`SUPERAGENT_API_KEY`），即可在手机/平板/其他电脑使用
聊天、任务执行、文件上传解析、审批、审计等全部功能。

## Web 控制台功能

- 💬 对话（`/chat`）
- 🚀 执行任务（`/run`）
- 📄 文件上传解析分析（`/upload`，支持 txt/md/json/csv/xlsx/docx）
- ✅ 待审批列表 + 放行/修改/驳回（`/pending` `/approve`）
- 📋 审计日志（`/audit`）

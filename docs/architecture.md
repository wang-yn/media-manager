# Architecture

## Runtime Shape

单容器默认运行：

- FastAPI 后端监听 `0.0.0.0:8000`
- 后端读取 `/config/config.toml`
- 后端同步扫描 `/media`
- 后端托管前端构建产物

本地开发时前后端分离：

- 后端：`PYTHONPATH=backend/src python3 -m media_manager.server`
- 前端：`npm run dev`，通过 Vite 代理访问后端

## 前端交互模型

- `#/` 是首屏，采用 Emby-like 媒体库入口，只展示媒体库卡片。
- `#/libraries/<id>` 展示单个媒体库内容，并提供媒体条目的行级操作。
- `#/settings` 承载系统状态、媒体目录管理和配置提示。
- 设置功能不得出现在首页。

## Media Model

电影和电视剧使用同一个扫描入口，输出不同类型：

- Movie: 目录或文件表示单部电影，例如 `Movie Name (2024)/Movie Name (2024).mkv`
- Series: 顶层目录表示剧集，季目录表示 Season，文件名或目录名识别 SxxEyy，例如 `Show/Season 01/Show - S01E01.mkv`
- Unknown: 扩展名是视频但暂时无法稳定归类

## Metadata Model

首版只支持 TMDB 手工刮削：

- 用户点击单个媒体条目的刮削按钮
- 后端按标题、年份、媒体类型搜索 TMDB
- 前端展示候选，用户选择后写 `.nfo`
- TMDB 密钥从 `TMDB_API_KEY` 或配置指定的环境变量读取

不做 provider 抽象、字幕下载、图片下载、后台任务或自动刮削。

## File Safety

所有整理类操作先做 dry-run：

- 计算目标路径
- 检查冲突
- 展示变更
- 用户确认后再执行

执行前重新校验预览结果。首版允许真实重命名，但只移动视频、同 stem 字幕、同 stem NFO，以及明确可识别的电影目录或剧集目录。

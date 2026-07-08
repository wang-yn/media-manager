# Architecture

## Runtime Shape

单容器默认运行：

- Python 后端监听 `0.0.0.0:8000`
- 后端读取 `/config/config.toml`
- 后端扫描 `/media`
- 后端托管前端构建产物

本地开发时前后端分离：

- 后端：`PYTHONPATH=backend/src python3 -m media_manager.server`
- 前端：`npm run dev`，通过 Vite 代理访问后端

## Media Model

电影和电视剧使用同一个扫描入口，输出不同类型：

- Movie: 目录或文件表示单部电影，例如 `Movie Name (2024)/Movie Name (2024).mkv`
- Series: 顶层目录表示剧集，季目录表示 Season，文件名或目录名识别 SxxEyy，例如 `Show/Season 01/Show - S01E01.mkv`
- Unknown: 扩展名是视频但暂时无法稳定归类

## Source Model

元数据和字幕下载都走 provider 适配器：

- core 只关心搜索、选择、下载/写入结果
- provider 只封装某个来源的认证、查询、限流、格式转换
- TOML 决定启用顺序和凭据位置

首版只定义配置和边界，不内置站点抓取逻辑。ChineseSubFinder 的可保留参考点是：

- 供应商有独立启用状态、根地址、搜索路径、下载限额。
- 电影和剧集走不同查询入口，剧集查询带 season/episode。
- 字幕候选结果要保留来源、语言、评分、偏移、扩展名、season/episode、是否整季包。
- Emby 字幕名可采用 `.chinese(简英,source).ass` 这类后缀，但作为可配置格式，不作为唯一格式。

不复制的旧复杂度：Go/Gin 结构、Chrome 自动化、Badger 缓存、时间轴修复流水线、历史 hotfix 层。

## File Safety

所有整理类操作先做 dry-run：

- 计算目标路径
- 检查冲突
- 展示变更
- 用户确认后再执行

首版只做扫描预览，不改动 `/media`。

# Media Manager MVP 设计

## 状态

- 日期：2026-07-08
- 状态：设计已批准，等待实现计划
- 范围：第一版可用的本地电影和剧集目录管理工具

## 目标

构建最小可用的 Web 工具，用于本地媒体整理：

- 添加媒体目录，并将目录标记为 `movie` 或 `series`。
- 展示已配置目录下扫描出的媒体条目。
- 从文件名和目录名解析基础元数据。
- 手工从 TMDB 刮削元数据。
- 将刮削结果写成 Emby/Jellyfin 兼容的旁路 `.nfo` 文件。
- 预览并执行目录和文件重命名。
- 同步操作失败时展示详细错误信息。

## 非目标

MVP 不包含：

- 后台任务。
- 自动周期扫描。
- 自动刮削。
- 批量刮削。
- 字幕下载。
- 数据库索引。
- 高级筛选、排序或复杂 UI 流程。
- 图片、海报下载。
- 完整演员和剧组信息。

## 架构

前端保持 React + Vite 单页工作台。

后端从 `http.server` 改为 FastAPI。FastAPI 负责请求解析、校验、路由和 JSON 错误响应。扫描、TMDB 访问、NFO 生成、配置写入、重命名规划保留为小型普通 Python 模块，方便绕过 HTTP 直接测试。

持久化状态保持最少：

- 媒体目录配置保存在 `/config/config.toml`。
- 刮削后的元数据保存在媒体文件旁边的 `.nfo` 文件中。
- MVP 不引入数据库、队列或缓存索引。

TMDB API 密钥从配置或环境变量读取，优先使用 `TMDB_API_KEY`。密钥本身不得提交到仓库。

## 用户流程

### 添加媒体目录

用户输入：

- 目录名称。
- 目录类型：`movie` 或 `series`。
- 媒体挂载目录内的绝对路径。

后端校验路径，将目录追加到 `/config/config.toml`，重新加载配置，并返回更新后的目录列表。前端保存后刷新媒体列表。

### 查看媒体列表

媒体列表由后端同步扫描已配置目录得到。

电影目录把一个视频文件或其父目录视为一部电影。剧集目录把库根目录下的第一层目录视为剧名，并尽量从文件名解析 `SxxEyy`。

列表行展示：

- 解析出的标题。
- 年份，如果能解析到。
- 类型。
- 剧集的季和集。
- 文件路径。
- 是否已有 `.nfo`。
- 该行最近一次操作错误，如果存在。

### 手工 TMDB 刮削

用户从某个媒体行发起刮削。

后端使用解析出的标题、年份和媒体类型搜索 TMDB。前端展示候选结果，不自动选择第一条。用户选择候选后，后端拉取所选 TMDB 详情并写入 `.nfo`。

电影输出：

- 电影目录内的 `movie.nfo`。

剧集输出：

- 剧集目录内的 `tvshow.nfo`。
- 如果能获得单集详情，在单集视频旁写同名 `.nfo`。

MVP 只写 Emby/Jellyfin 可读取的基础字段：

- 标题。
- 原始标题，如果有。
- 年份。
- 简介。
- TMDB ID。
- 媒体类型。
- 单集的季和集字段。

### 重命名预览和执行

用户从某个媒体行请求重命名预览。

后端基于现有整理模板计算目标路径，返回源路径、目标路径、相关旁路文件和阻塞冲突。只有预览没有阻塞冲突时，前端才允许执行。

用户确认后执行预览结果。执行是同步操作，返回已变更路径或结构化错误。

重命名执行覆盖：

- 视频文件。
- 同 stem 的字幕文件。
- 同 stem 的单集 `.nfo` 文件。
- 仅在能明确识别且不会触碰无关父目录时，才重命名电影目录或剧集根目录。

## API

- `GET /api/health`
- `GET /api/libraries`
- `POST /api/libraries`
- `GET /api/media`
- `POST /api/media/{id}/metadata/search`
- `POST /api/media/{id}/metadata/apply`
- `POST /api/media/{id}/rename/preview`
- `POST /api/media/{id}/rename/apply`

媒体 ID 由当前文件路径生成稳定 hash。每次操作都会重新扫描已配置目录，并通过 ID 找回当前文件路径。如果文件已经移动，API 返回未找到错误，前端刷新列表。

## 错误处理

所有操作都是同步操作。失败时返回如下 JSON：

```json
{
  "error": {
    "code": "tmdb_request_failed",
    "message": "TMDB request failed",
    "detail": "HTTP 401 Unauthorized",
    "path": "/media/movies/example/movie.mkv"
  }
}
```

前端展示 `message`、`detail` 和相关路径。前端不把后端详细错误替换成泛化文案。

预期错误码包括：

- `invalid_library_path`
- `config_write_failed`
- `media_not_found`
- `tmdb_missing_api_key`
- `tmdb_request_failed`
- `tmdb_no_candidate_selected`
- `nfo_write_failed`
- `rename_conflict`
- `rename_outside_library`
- `rename_failed`

## 文件安全

重命名操作限制在已配置的媒体目录根路径内。

预览阶段检查：

- 目标路径仍在同一个已配置媒体目录根路径内。
- 目标路径尚不存在。
- 同一次操作没有重复目标。
- 相关旁路文件只有在与媒体文件同 stem 时才移动。

执行阶段会重新校验预览结果后再改文件。如果校验失败，不执行任何重命名。

## 前端形态

MVP 保持单页工作台，包含三块：

- 媒体目录：列表和新增表单。
- 媒体列表：扫描行、解析出的元数据和 NFO 状态。
- 行操作：刮削元数据、选择 TMDB 候选、预览重命名、执行重命名。

界面保持朴素、偏操作台。不需要落地页、影视门户式设计或复杂导航。

## 测试

后端测试覆盖：

- 电影和剧集扫描。
- 媒体目录配置追加。
- 使用假响应验证 TMDB 客户端行为。
- NFO XML 生成。
- 重命名预览冲突检测。
- 视频、同 stem 字幕、同 stem NFO 的重命名执行。
- FastAPI 主要成功路径和一个结构化失败路径。

前端验证覆盖：

- TypeScript 构建。
- 加载、错误、空媒体列表、媒体行等基础渲染状态。

测试不得调用真实 TMDB API。

## 实现备注

尽量沿用现有项目结构，保持改动聚焦：

- 用 FastAPI 替换后端 HTTP 入口。
- 扫描逻辑继续保留为普通模块。
- 新增小模块处理 TMDB、NFO、配置写入和重命名规划。
- 只因启动命令和依赖变化更新 Docker 与 README。

MVP 跳过：自定义任务系统、数据库 schema、provider 抽象、UI 框架。只有第一版真实工作流证明需要时再添加。

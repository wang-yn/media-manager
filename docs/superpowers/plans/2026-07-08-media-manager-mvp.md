# Media Manager MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现第一版 Media Manager：添加媒体目录、同步扫描、TMDB 手工刮削、旁路 NFO、重命名预览和执行。

**Architecture:** 后端改为 FastAPI，HTTP 层只做请求校验和错误响应；扫描、配置写入、TMDB、NFO、重命名保持普通 Python 模块。前端保持单页 React 工作台，所有操作同步调用 API 并展示详细错误。

**Tech Stack:** Python 3.11+、FastAPI、Uvicorn、标准库 `unittest`/`tomllib`/`urllib`/`xml.etree.ElementTree`、React、TypeScript、Vite。

---

## 文件结构

- 修改 `backend/pyproject.toml`：声明 FastAPI、Uvicorn、HTTP 测试所需的 httpx。
- 修改 `backend/src/media_manager/config.py`：支持新增媒体目录并写入 TOML。
- 修改 `backend/src/media_manager/media.py`：媒体条目增加稳定 ID、NFO 状态和可用于操作的结构。
- 新增 `backend/src/media_manager/errors.py`：统一业务错误和 FastAPI 错误输出。
- 新增 `backend/src/media_manager/tmdb.py`：最小 TMDB search/details 客户端，可注入 fake opener 测试。
- 新增 `backend/src/media_manager/nfo.py`：生成电影、剧集、单集 NFO。
- 新增 `backend/src/media_manager/rename.py`：生成重命名预览并安全执行。
- 修改 `backend/src/media_manager/server.py`：替换为 FastAPI 应用和静态文件托管。
- 修改 `backend/tests/test_media.py`：保留扫描测试并扩展 ID/NFO 状态。
- 新增 `backend/tests/test_config.py`、`test_tmdb.py`、`test_nfo.py`、`test_rename.py`、`test_server.py`。
- 修改 `frontend/src/App.tsx`、`frontend/src/style.css`：实现 MVP 单页交互。
- 修改 `README.md`、`Dockerfile`、`config/config.example.toml`：同步启动方式和配置。

## Task 1: 配置写入

**Files:**
- Modify: `backend/src/media_manager/config.py`
- Test: `backend/tests/test_config.py`

- [ ] 写失败测试：`append_library()` 会把 `[[libraries]]` 追加到 TOML，保留原有配置。
- [ ] 运行：`PYTHONPATH=backend/src python3 -m unittest backend.tests.test_config`，预期因为函数不存在失败。
- [ ] 实现最少 `append_library(path, name, kind, library_path)`，只写需要的 TOML 字段。
- [ ] 运行同一测试，预期通过。

## Task 2: 扫描结果可被 API 操作

**Files:**
- Modify: `backend/src/media_manager/media.py`
- Test: `backend/tests/test_media.py`

- [ ] 写失败测试：扫描结果包含稳定 `id`、`nfo` 状态和 `library_path`。
- [ ] 运行：`PYTHONPATH=backend/src python3 -m unittest backend.tests.test_media`，预期失败。
- [ ] 实现 `MediaItem.id`、`nfo_path`、`has_nfo`、`library_path`。
- [ ] 运行同一测试，预期通过。

## Task 3: NFO 生成

**Files:**
- Create: `backend/src/media_manager/nfo.py`
- Test: `backend/tests/test_nfo.py`

- [ ] 写失败测试：电影写 `movie.nfo`，剧集写 `tvshow.nfo`，单集写同名 `.nfo`。
- [ ] 运行：`PYTHONPATH=backend/src python3 -m unittest backend.tests.test_nfo`，预期导入失败。
- [ ] 用 `xml.etree.ElementTree` 实现基础字段写入。
- [ ] 运行同一测试，预期通过。

## Task 4: 重命名预览和执行

**Files:**
- Create: `backend/src/media_manager/rename.py`
- Test: `backend/tests/test_rename.py`

- [ ] 写失败测试：预览检测目标冲突、越界目标；执行移动视频、同 stem 字幕和同 stem NFO。
- [ ] 运行：`PYTHONPATH=backend/src python3 -m unittest backend.tests.test_rename`，预期导入失败。
- [ ] 实现 `preview_rename()` 和 `apply_rename()`，执行前重新校验。
- [ ] 运行同一测试，预期通过。

## Task 5: TMDB 客户端

**Files:**
- Create: `backend/src/media_manager/tmdb.py`
- Test: `backend/tests/test_tmdb.py`

- [ ] 写失败测试：缺少 API key 返回业务错误；fake HTTP 响应能转成候选和详情。
- [ ] 运行：`PYTHONPATH=backend/src python3 -m unittest backend.tests.test_tmdb`，预期导入失败。
- [ ] 用标准库 `urllib.request` 实现 search/details，测试不打真实网络。
- [ ] 运行同一测试，预期通过。

## Task 6: FastAPI API

**Files:**
- Modify: `backend/src/media_manager/server.py`
- Create: `backend/src/media_manager/errors.py`
- Test: `backend/tests/test_server.py`

- [ ] 写失败测试：`GET /api/health`、`GET/POST /api/libraries`、`GET /api/media`、结构化错误响应。
- [ ] 运行：`PYTHONPATH=backend/src python3 -m unittest backend.tests.test_server`，预期 FastAPI 或接口失败。
- [ ] 实现 FastAPI app、业务错误处理、静态文件托管和 API 路由。
- [ ] 运行同一测试，预期通过。

## Task 7: 前端工作台

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/style.css`

- [ ] 更新类型和 API 调用，支持目录新增、媒体列表、TMDB 候选、写 NFO、预览/执行重命名。
- [ ] 显示后端 `error.message`、`error.detail`、`error.path`。
- [ ] 运行：`cd frontend && npm run build`，预期通过。

## Task 8: 文档、全量验证和提交

**Files:**
- Modify: `README.md`
- Modify: `Dockerfile`
- Modify: `config/config.example.toml`

- [ ] README 改为 FastAPI/Uvicorn 启动说明，并说明 `TMDB_API_KEY`。
- [ ] Dockerfile 使用 Uvicorn 启动。
- [ ] 运行：`PYTHONPATH=backend/src python3 -m unittest discover backend/tests`。
- [ ] 运行：`cd frontend && npm run build`。
- [ ] 运行：`git diff --check`。
- [ ] 提交：`git add ... && git commit -m "feat: implement media manager mvp"`。

## 自检

- spec 中的添加目录、媒体列表、TMDB 手工刮削、NFO、重命名预览/执行都有任务覆盖。
- 非目标没有进入计划：不做后台任务、自动扫描、数据库、批量刮削、字幕下载、图片下载。
- 所有计划文档正文为中文，保留必要英文技术名和命令。

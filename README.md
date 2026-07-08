# Media Manager

影视媒体库整理、元数据刮削、字幕下载工具。目标运行形态是 Docker 容器，用户持久化挂载：

- `/config`：TOML 配置、任务状态、缓存索引
- `/media`：电影、电视剧媒体库

## 当前状态

这是第一版仓库初始化：

- Python 后端：FastAPI，同步提供健康检查、媒体目录管理、扫描、TMDB 刮削、NFO 写入、重命名预览和执行。
- React + TypeScript 前端：单页工作台，展示后端状态、媒体目录、影视列表和行内操作。
- TOML 配置：定义媒体库、TMDB 密钥环境变量、目录整理模板。
- Docker：单容器运行后端并托管前端静态文件。

## 本地开发

后端：

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e backend
TMDB_API_KEY=你的密钥 PYTHONPATH=backend/src .venv/bin/python -m media_manager.server
```

前端：

```bash
cd frontend
npm install
npm run dev
```

测试：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
cd frontend && npm run build
```

## API

- `GET /api/health`
- `GET /api/libraries`
- `POST /api/libraries`
- `GET /api/media`
- `POST /api/media/{id}/metadata/search`
- `POST /api/media/{id}/metadata/apply`
- `POST /api/media/{id}/rename/preview`
- `POST /api/media/{id}/rename/apply`

默认开发配置读取 `config/config.example.toml`。容器内默认读取 `/config/config.toml`，不存在时可用示例配置启动。

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

## Docker 部署

准备配置和媒体目录：

```bash
mkdir -p config media/movies media/tv
cp -n config/config.example.toml config/config.toml
```

`config/config.toml` 中的媒体库路径使用容器内路径，例如 `/media/movies`、`/media/tv`。宿主机目录通过 `-v` 挂载到容器内的 `/config` 和 `/media`。

构建镜像：

```bash
docker build -t media-manager:local .
```

启动容器：

```bash
docker run -d \
  --name media-manager \
  -p 8000:8000 \
  -e MEDIA_MANAGER_HOST=0.0.0.0 \
  -e MEDIA_MANAGER_PORT=8000 \
  -e TMDB_API_KEY=你的_TMDB_API_KEY \
  -e ASSRT_API_TOKEN=你的_ASSRT_API_TOKEN \
  -v "$PWD/config:/config" \
  -v "$PWD/media:/media" \
  --restart unless-stopped \
  media-manager:local
```

使用已发布镜像：

```bash
docker pull ghcr.io/wang-yn/media-manager:v1.0.1
docker run -d \
  --name media-manager \
  -p 8000:8000 \
  -e MEDIA_MANAGER_HOST=0.0.0.0 \
  -e MEDIA_MANAGER_PORT=8000 \
  -e TMDB_API_KEY=你的_TMDB_API_KEY \
  -e ASSRT_API_TOKEN=你的_ASSRT_API_TOKEN \
  -v "$PWD/config:/config" \
  -v "$PWD/media:/media" \
  --restart unless-stopped \
  ghcr.io/wang-yn/media-manager:v1.0.1
```

访问 `http://localhost:8000`。检查状态：

```bash
curl http://localhost:8000/api/health
```

停止并删除容器：

```bash
docker stop media-manager
docker rm media-manager
```

## Docker Compose 部署

准备配置：

```bash
mkdir -p config media/movies media/tv
cp -n config/config.example.toml config/config.toml
```

设置密钥并启动：

```bash
export TMDB_API_KEY=你的_TMDB_API_KEY
export ASSRT_API_TOKEN=你的_ASSRT_API_TOKEN
docker compose up -d --build
```

常用命令：

```bash
docker compose logs -f media-manager
docker compose ps
docker compose down
```

启动后访问 `http://localhost:8000`。如果不需要字幕下载，可以不设置 `ASSRT_API_TOKEN`；如果不需要 TMDB 元数据刮削，可以不设置 `TMDB_API_KEY`。

注意：Docker 容器内的媒体路径必须使用容器路径，例如 `/media/movies`、`/media/tv`，不要写宿主机绝对路径。容器需要监听 `0.0.0.0:8000`；如果复用本地开发的 `config/config.toml`，请保留上面的 `MEDIA_MANAGER_HOST` 和 `MEDIA_MANAGER_PORT` 环境变量覆盖。

## API

- `GET /api/health`
- `GET /api/libraries`
- `POST /api/libraries`
- `GET /api/media`
- `POST /api/media/{id}/metadata/search`
- `POST /api/media/{id}/metadata/apply`
- `POST /api/media/{id}/rename/preview`
- `POST /api/media/{id}/rename/apply`

本地开发默认优先读取 `config/config.toml`，不存在时读取 `config/config.example.toml`。容器内默认读取 `/config/config.toml`。

# Media Manager

影视媒体库整理、元数据刮削、字幕下载工具。


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

访问 `http://localhost:8000`。

停止并删除容器：

```bash
docker stop media-manager
docker rm media-manager
```

## Docker Compose 部署


```yaml
services:
  media-manager:
    image: ghcr.io/wang-yn/media-manager:latest
    container_name: media-manager
    environment:
      - TZ=Asia/Shanghai
      - MEDIA_MANAGER_HOST=0.0.0.0
      - MEDIA_MANAGER_PORT=8000
      - TMDB_API_KEY=${TMDB_API_KEY:-}
      - ASSRT_API_TOKEN=${ASSRT_API_TOKEN:-}
    volumes:
      - ./config:/config
      - ./media:/media
    ports:
      - "8000:8000"
    restart: unless-stopped
```

启动后访问 `http://localhost:8000`


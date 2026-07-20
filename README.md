# Media Manager

影视媒体库整理、元数据刮削、字幕下载工具。


## 本地开发

后端：

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e backend
export MEDIA_MANAGER_PUBLIC_URL="https://media.example.com"
export MEDIA_MANAGER_SESSION_SECRET="$(openssl rand -hex 32)"
export GITHUB_OAUTH_CLIENT_ID="你的_GitHub_OAuth_Client_ID"
export GITHUB_OAUTH_CLIENT_SECRET="你的_GitHub_OAuth_Client_Secret"
export GITHUB_ALLOWED_USERS="wang-yn"
export TMDB_API_KEY="你的_TMDB_API_KEY"
PYTHONPATH=backend/src .venv/bin/python -m media_manager.server
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite dev server 仅用于界面开发，不作为 GitHub OAuth 端到端入口。调试完整登录流程时，先执行 `npm run build --prefix frontend` 确保后端静态目录有构建产物，再通过 HTTPS 反向代理把 `MEDIA_MANAGER_PUBLIC_URL` 的全部请求转发到后端 8000，并从该 HTTPS 地址访问；不要从 `localhost:5173` 验证登录。

测试：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
cd frontend && npm run build
```

## GitHub 登录配置

在 GitHub 进入 `Settings -> Developer settings -> OAuth Apps`，创建 OAuth App：

- Homepage URL: `https://media.example.com`
- Authorization callback URL: `https://media.example.com/auth/github/callback`

生成会话密钥：

```bash
openssl rand -hex 32
```

启动前导出五项认证配置：

```bash
export MEDIA_MANAGER_PUBLIC_URL="https://media.example.com"
export MEDIA_MANAGER_SESSION_SECRET="上一步生成的_64位_hex"
export GITHUB_OAUTH_CLIENT_ID="你的_GitHub_OAuth_Client_ID"
export GITHUB_OAUTH_CLIENT_SECRET="你的_GitHub_OAuth_Client_Secret"
export GITHUB_ALLOWED_USERS="wang-yn,other-user"
```

`GITHUB_ALLOWED_USERS` 使用英文逗号分隔，匹配 GitHub 登录名时大小写不敏感。任一认证变量缺失或非法时，后端会拒绝启动。

## Docker 部署

```bash
docker pull ghcr.io/wang-yn/media-manager:v1.1.3
docker run -d \
  --name media-manager \
  -p 8000:8000 \
  -e MEDIA_MANAGER_HOST=0.0.0.0 \
  -e MEDIA_MANAGER_PORT=8000 \
  -e MEDIA_MANAGER_PUBLIC_URL="$MEDIA_MANAGER_PUBLIC_URL" \
  -e MEDIA_MANAGER_SESSION_SECRET="$MEDIA_MANAGER_SESSION_SECRET" \
  -e GITHUB_OAUTH_CLIENT_ID="$GITHUB_OAUTH_CLIENT_ID" \
  -e GITHUB_OAUTH_CLIENT_SECRET="$GITHUB_OAUTH_CLIENT_SECRET" \
  -e GITHUB_ALLOWED_USERS="$GITHUB_ALLOWED_USERS" \
  -e TMDB_API_KEY=你的_TMDB_API_KEY \
  -e ASSRT_API_TOKEN=你的_ASSRT_API_TOKEN \
  -v "$PWD/config:/config" \
  -v "$PWD/media:/media" \
  --restart unless-stopped \
  ghcr.io/wang-yn/media-manager:v1.1.3
```

访问 `MEDIA_MANAGER_PUBLIC_URL` 对应的 HTTPS 地址，例如 `https://media.example.com`。容器内的 8000 端口通常由 HTTPS 反向代理转发；Secure Cookie 要求浏览器通过 HTTPS 访问。

停止并删除容器：

```bash
docker stop media-manager
docker rm media-manager
```

## Docker Compose 部署


```yaml
services:
  media-manager:
    image: ghcr.io/wang-yn/media-manager:v1.1.3
    container_name: media-manager
    environment:
      - TZ=Asia/Shanghai
      - MEDIA_MANAGER_HOST=0.0.0.0
      - MEDIA_MANAGER_PORT=8000
      - MEDIA_MANAGER_PUBLIC_URL=${MEDIA_MANAGER_PUBLIC_URL}
      - MEDIA_MANAGER_SESSION_SECRET=${MEDIA_MANAGER_SESSION_SECRET}
      - GITHUB_OAUTH_CLIENT_ID=${GITHUB_OAUTH_CLIENT_ID}
      - GITHUB_OAUTH_CLIENT_SECRET=${GITHUB_OAUTH_CLIENT_SECRET}
      - GITHUB_ALLOWED_USERS=${GITHUB_ALLOWED_USERS}
      - TMDB_API_KEY=${TMDB_API_KEY:-}
      - ASSRT_API_TOKEN=${ASSRT_API_TOKEN:-}
    volumes:
      - ./config:/config
      - ./media:/media
    ports:
      - "8000:8000"
    restart: unless-stopped
```

启动后访问 `MEDIA_MANAGER_PUBLIC_URL` 对应的 HTTPS 地址，例如 `https://media.example.com`。容器内的 8000 端口通常由 HTTPS 反向代理转发；Secure Cookie 要求浏览器通过 HTTPS 访问。

# Media Manager

影视媒体库整理、元数据刮削、字幕下载工具。目标运行形态是 Docker 容器，用户持久化挂载：

- `/config`：TOML 配置、任务状态、缓存索引
- `/media`：电影、电视剧媒体库

## 当前状态

这是第一版仓库初始化：

- Python 后端：无框架依赖，提供健康检查、配置读取、媒体目录扫描预览。
- React + TypeScript 前端：管理工作台壳，展示后端状态、媒体库、扫描结果。
- TOML 配置：定义媒体库、元数据源、字幕源、目录整理模板。
- Docker：单容器运行后端并托管前端静态文件。

## 本地开发

后端：

```bash
PYTHONPATH=backend/src python3 -m media_manager.server
```

前端：

```bash
cd frontend
npm install
npm run dev
```

测试：

```bash
PYTHONPATH=backend/src python3 -m unittest discover backend/tests
cd frontend && npm run build
```

## API

- `GET /api/health`
- `GET /api/config`
- `GET /api/scan`

默认开发配置读取 `config/config.example.toml`。容器内默认读取 `/config/config.toml`，不存在时可用示例配置启动。

# assrt 字幕下载接入设计

## 状态

- 日期：2026-07-09
- 状态：设计已批准，等待实现计划
- 范围：接入 assrt.net API，为单个媒体条目提供手动搜索字幕、候选选择和下载到视频旁边的能力。

## 背景

当前 MVP 已能扫描媒体目录、显示已有旁路字幕、手工刮削 TMDB 元数据并执行安全重命名。字幕下载仍是非目标，但用户现在确认要分析并规划接入 assrt.net。

assrt 官方 API 适合首版做同步手动下载：

- `sub/search` 可以按视频文件名搜索字幕。
- `sub/detail` 才返回下载地址和压缩包内文件列表。
- `user/quota` 可以查询剩余配额。
- 下载地址有时效，不能缓存。

测试 token 的配额是 5 次/分钟。首版必须避免批量、自动和预取详情，否则很容易打满配额。

## 目标

- 单个媒体条目提供“搜索字幕”操作。
- 默认用视频文件名去 assrt 搜索，而不是用清理后的标题。
- 用户在弹窗中选择一个字幕候选。
- 用户确认后下载字幕到视频文件旁边。
- 下载后媒体列表刷新，并通过现有 `subtitles` 字段展示新字幕。
- 缺少 token、请求失败、配额超限、不支持的下载内容都返回结构化错误。

## 非目标

- 不做自动扫描字幕。
- 不做批量字幕下载。
- 不做后台任务或队列。
- 不做自动选择最佳候选。
- 不缓存 assrt 下载 URL。
- 不解压 rar、zip、7z 等压缩包。
- 不做多字幕源抽象。
- 不新增依赖。

## API 文档依据

来源：https://assrt.net/api/doc

本设计只使用这些接口：

- `GET https://api.assrt.net/v1/sub/search`
- `GET https://api.assrt.net/v1/sub/detail`
- `GET https://api.assrt.net/v1/user/quota`

认证使用 `Authorization: Bearer <token>`，不把 token 放进 URL，减少日志泄露风险。

## 用户流程

### 搜索字幕

用户在媒体库详情页点击某条媒体的“字幕”或“搜索字幕”。

前端打开弹窗并调用后端搜索接口。默认搜索词为视频文件 stem：

- `The.Matrix.1999.1080p.BluRay.x264.DTS-FGT.mkv`
- 搜索词：`The.Matrix.1999.1080p.BluRay.x264.DTS-FGT`

后端调用 assrt：

- `q=<视频文件 stem>`
- `cnt=10`
- `no_muxer=1`

`no_muxer=1` 让 assrt 自己忽略压制组和视频参数，比本项目再写一套字幕搜索清洗规则更稳。

### 展示候选

弹窗候选列表展示：

- 字幕 ID。
- 字幕名 `native_name`。
- 匹配视频名 `videoname`。
- 语言描述 `lang.desc`。
- 字幕格式 `subtype`。
- 评分 `vote_score`。
- 字幕组 `release_site`。
- 上传时间 `upload_time`。

搜索结果阶段不调用 `detail`。用户没有选择前不消耗额外配额。

### 下载字幕

用户选择候选并点击下载后：

1. 后端调用 `sub/detail?id=<字幕 ID>`。
2. 从详情结果中挑选可直接下载的字幕文件。
3. 下载字幕内容。
4. 保存到视频旁边。
5. 刷新媒体列表。

首版优先选择 `filelist` 中扩展名为 `.srt`、`.ass`、`.ssa` 的文件。若没有可直接下载的字幕文件，返回 `assrt_unsupported_archive`，提示当前只支持直接下载字幕文件。

## 文件命名

首版保存为：

```text
<视频文件名>.zh.<字幕扩展名>
```

示例：

```text
The.Matrix.1999.1080p.BluRay.x264.DTS-FGT.zh.srt
Pantheon - S01E03.zh.ass
```

规则：

- 使用视频文件 stem，不使用候选字幕文件名。
- 默认语言后缀固定为 `.zh`。
- 字幕扩展名继承下载文件扩展名。
- 如果目标文件已存在，不覆盖，返回冲突错误。

## 后端设计

新增 `backend/src/media_manager/assrt.py`，形状沿用 `TMDBClient`：

- `search(query: str) -> list[dict[str, object]]`
- `detail(subtitle_id: int) -> dict[str, object]`
- `download(url: str) -> bytes`
- `quota() -> dict[str, object]`

客户端职责：

- 读取 token。
- 设置 `Authorization: Bearer <token>`。
- 解析 JSON。
- 将 `status != 0` 转为 `AppError`。
- 将 HTTP 或网络异常转为 `AppError`。

新增下载服务函数可以放在 `assrt.py` 或很薄的 `subtitles.py`：

- 找到当前媒体条目。
- 生成搜索词。
- 从 detail 中挑选可直接下载文件。
- 校验目标路径不覆盖已有文件。
- 写入字幕文件。

保持最小文件数，除非实现时 `assrt.py` 变得过长。

## 配置

`config/config.example.toml` 增加：

```toml
[assrt]
token_env = "ASSRT_API_TOKEN"
```

运行时读取顺序：

1. `ASSRT_API_TOKEN` 或配置指定的环境变量。
2. `[assrt].token`。

示例配置不写真实 token。

`GET /api/health` 增加 assrt 状态：

```json
{
  "assrt": "configured"
}
```

只返回是否已配置，不返回 token 内容。

## 后端 API

新增：

```http
POST /api/media/{id}/subtitles/search
```

请求体可选：

```json
{
  "query": "The.Matrix.1999.1080p.BluRay.x264.DTS-FGT"
}
```

不传 `query` 时使用视频文件 stem。返回：

```json
{
  "results": [
    {
      "id": 123456,
      "native_name": "...",
      "videoname": "...",
      "lang": "双语",
      "subtype": "Subrip(srt)",
      "vote_score": 12,
      "release_site": "...",
      "upload_time": "2020-01-01 00:00:00"
    }
  ]
}
```

新增：

```http
POST /api/media/{id}/subtitles/download
```

请求体：

```json
{
  "subtitle_id": 123456
}
```

返回：

```json
{
  "path": "/media/movies/The Matrix/The.Matrix.1999.1080p.BluRay.x264-DTS.zh.srt"
}
```

可选新增：

```http
GET /api/subtitles/quota
```

只在前端需要显示剩余配额时实现。首版可以先不做，避免多消耗一次 API。

## 前端设计

在媒体库详情页为每个媒体条目增加“字幕”操作。

弹窗状态：

- 当前媒体条目。
- 搜索关键字。
- 候选列表。
- 当前选中的候选。
- 忙碌状态。
- 错误信息。

交互：

- 打开弹窗后立即搜索。
- 允许用户修改搜索词并重新搜索。
- 候选列表中点击一项后启用“下载”按钮。
- 下载成功后关闭弹窗并刷新媒体列表。
- 下载失败时保留弹窗并显示结构化错误。

## 错误处理

新增错误码：

- `assrt_missing_token`：缺少 assrt token。
- `assrt_request_failed`：HTTP、网络或 JSON 解析失败。
- `assrt_api_error`：assrt 返回 `status != 0`。
- `assrt_quota_exceeded`：assrt 错误码 `30900`。
- `assrt_keyword_too_short`：关键词不足 3 个字符。
- `assrt_subtitle_not_found`：详情结果为空或字幕不存在。
- `assrt_unsupported_archive`：详情只有压缩包下载，没有可直接下载字幕文件。
- `subtitle_target_exists`：目标字幕文件已存在。
- `subtitle_write_failed`：写入字幕文件失败。

错误展示沿用现有结构化错误 UI。

## 配额策略

测试 token 配额为 5 次/分钟。首版策略：

- 一次搜索消耗 1 次。
- 用户选中并下载消耗至少 1 次详情请求，下载文件本身是否计入由 assrt 服务决定。
- 不批量。
- 不自动请求每条候选详情。
- 不在弹窗打开时额外调用 `quota`。
- 发生 `30900` 时直接提示配额超限，让用户稍后再试。

如果后续需要批量字幕下载，再增加后台任务和简单节流。

## 文件安全

- 下载目标必须在当前视频文件同目录。
- 目标文件名只由当前视频 stem、固定 `.zh` 和安全扩展名组成。
- 只允许 `.srt`、`.ass`、`.ssa`。
- 不覆盖已有文件。
- 不跟随用户传入的下载文件名写路径。
- 不保存下载 URL。

## 实现边界

允许修改：

- `backend/src/media_manager/assrt.py`
- `backend/src/media_manager/server.py`
- `backend/src/media_manager/config.py`
- `backend/tests/test_assrt.py`
- `backend/tests/test_server.py`
- `config/config.example.toml`
- `frontend/src/App.tsx`
- `frontend/src/style.css`

不需要修改：

- TMDB 客户端。
- NFO 写入。
- 重命名逻辑。
- Dockerfile。
- README 以外的产品文档。

## 测试与验证

后端测试：

- 缺少 token 时返回 `assrt_missing_token`。
- 搜索请求使用 `Authorization: Bearer`。
- 搜索结果映射为前端需要的候选字段。
- `status != 0` 映射为结构化错误。
- `30900` 映射为 `assrt_quota_exceeded`。
- 下载时只保存 `.srt/.ass/.ssa`。
- 目标字幕已存在时不覆盖。
- 只有压缩包下载时返回 `assrt_unsupported_archive`。

前端验证：

- `cd frontend && npm run build`
- 手动打开字幕弹窗，确认默认搜索、修改关键词、选择候选、下载成功和错误展示。

全量验证：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
cd frontend && npm run build
git diff --check
```

敏感信息检查：

```bash
rg -n --no-ignore 'ASSRT_API_TOKEN|token\s*=\s*"[A-Za-z0-9]{20,}"|api_key\s*=\s*"[A-Za-z0-9]{20,}"' . -g '!frontend/node_modules/**' -g '!frontend/dist/**' -g '!.venv/**' -g '!.git/**'
```

检查结果不得包含真实 token。

## 设计自检

- 已限定为单条媒体手动搜索和下载。
- 已避开后台任务、批量下载和自动下载。
- 已明确不缓存下载 URL。
- 已明确测试 token 不写入仓库。
- 已考虑 5 次/分钟配额。
- 已明确首版字幕命名为 `<视频文件名>.zh.<字幕扩展名>`。
- 已避免新增依赖和 provider 抽象。

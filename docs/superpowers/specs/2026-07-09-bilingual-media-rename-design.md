# 双语媒体命名规范设计

## 状态

- 日期：2026-07-09
- 状态：设计待确认
- 范围：让重命名预览和执行遵循“中英文名 + 年份 + 标准剧集层级”的媒体整理规范

## 背景

当前电影重命名已接近 `片名 (年份)/片名 (年份).扩展名`，但剧集目录会从 `Pantheon (2022)` 预览为 `Pantheon`，缺少年份，也没有同时包含中英文名。

本轮目标是让文件结构更符合常见刮削器识别习惯：

- 电影必须有专属文件夹。
- 电影文件夹和视频文件名必须带完整片名和圆括号年份。
- 剧集必须是 `剧集文件夹 -> 季度文件夹 -> 单集文件` 三层结构。
- 单集文件必须包含 `SxxExx`，这是识别季集的核心依据。
- 视频扩展名不固定为 `.mkv`，重命名必须保留原视频扩展名。

## 目标

- 电影目标路径：
  - `英文名 - 中文名 (年份)/英文名 - 中文名 (年份).原扩展名`
- 剧集目标路径：
  - `英文名 - 中文名 (年份)/Season 01/英文名 - 中文名 - S01E03.原扩展名`
- 如果只有一个标题，退化为：
  - 电影：`标题 (年份)/标题 (年份).原扩展名`
  - 剧集：`标题 (年份)/Season 01/标题 - S01E03.原扩展名`
- 如果中英文标题相同，不重复拼接。
- 保留当前重命名 dry-run 和冲突检查。
- 保留同 stem 字幕、同 stem NFO、电影 `movie.nfo` 的移动行为。

## 非目标

- 不新增数据库。
- 不新增后台任务。
- 不做批量重命名。
- 不引入新的刮削源。
- 不保存完整元数据模型。
- 不生成单集标题，例如 `Episode Name`。

## 标题来源

重命名优先从 NFO 读取标题：

- `title` 作为中文名或本地化标题。
- `originaltitle` 作为英文名或原始标题。
- `year` 作为年份。

如果 NFO 不存在或字段缺失，则退回到当前扫描得到的 `MediaItem.title` 和 `MediaItem.year`。

示例：

```xml
<title>万神殿</title>
<originaltitle>Pantheon</originaltitle>
<year>2022</year>
```

生成基础标题：

```text
Pantheon - 万神殿
```

生成剧集目录：

```text
Pantheon - 万神殿 (2022)
```

## 扩展名规则

视频扩展名必须从原文件继承，不写死。

当前扫描器支持的扩展名包括：

- `.mkv`
- `.mp4`
- `.avi`
- `.mov`
- `.wmv`
- `.m4v`
- `.ts`

如果未来扩展 `VIDEO_EXTENSIONS`，重命名逻辑不需要同步维护扩展名列表，只使用当前视频路径的 `suffix`。

## 命名规则

### 电影

输入：

```text
Movies/Old Name/old.name.mp4
movie.nfo: title=沙丘, originaltitle=Dune, year=2021
```

输出：

```text
Movies/Dune - 沙丘 (2021)/Dune - 沙丘 (2021).mp4
Movies/Dune - 沙丘 (2021)/movie.nfo
```

### 剧集

输入：

```text
TV/Pantheon (2022)/Season 01/Pantheon - S01E03.mkv
tvshow.nfo: title=万神殿, originaltitle=Pantheon, year=2022
```

输出：

```text
TV/Pantheon - 万神殿 (2022)/Season 01/Pantheon - 万神殿 - S01E03.mkv
```

单集 NFO 和同 stem 字幕跟随单集文件名移动。

## 冲突和安全

- 目标路径必须仍在当前媒体库目录内。
- 目标已存在且不是当前源文件时，预览返回冲突。
- 多个源文件指向同一目标时，预览返回冲突。
- 执行前继续重新计算预览。
- 执行后只清理空目录，不删除非空目录。

## 配置影响

首版实现不增加模板配置解析。`config/config.example.toml` 中的整理模板只作为默认规范说明同步更新，真实目标路径由 `rename.py` 按上述规则生成。

后续如果需要可配置模板，再单独设计。

## 测试与验证

必须增加后端测试：

- 电影从 `movie.nfo` 读取中英文名和年份，保留 `.mp4` 等原扩展名。
- 剧集从 `tvshow.nfo` 读取中英文名和年份，保持三层结构并保留 `SxxExx`。
- 只有一个标题时不重复拼接。
- 坏或缺失 NFO 时回退到当前扫描标题。

必须运行：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
git diff --check
```

如涉及前端展示变化，再运行：

```bash
cd frontend && npm run build
```

## 设计自检

- 已覆盖电影专属文件夹。
- 已覆盖电影和剧集年份。
- 已覆盖剧集三层结构。
- 已覆盖 `SxxExx`。
- 已明确视频扩展名不固定为 `.mkv`。
- 未引入数据库、后台任务或新依赖。

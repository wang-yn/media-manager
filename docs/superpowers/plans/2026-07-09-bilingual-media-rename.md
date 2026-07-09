# 双语媒体命名规范 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让重命名预览和执行按 NFO 中的中英文标题与年份生成电影、剧集目标路径，并保留原视频扩展名。

**Architecture:** 不新增数据库、不扩前端交互。后端 `rename.py` 在计算目标路径时读取 `movie.nfo` 或 `tvshow.nfo` 的 `title/originaltitle/year`，生成稳定的双语基础名；读不到 NFO 时退回现有 `MediaItem.title/year`。现有 dry-run、冲突检查、sidecar 移动和空目录清理保持不变。

**Tech Stack:** Python stdlib `xml.etree.ElementTree`、现有 `unittest` 后端测试、TOML 示例配置、中文架构文档。

---

## 文件结构

- 修改 `backend/tests/test_rename.py`：新增 NFO 驱动的电影/剧集命名测试，覆盖 `.mp4` 扩展名保留、双语标题、不重复标题和缺失 NFO 回退。
- 修改 `backend/src/media_manager/rename.py`：新增 NFO 读取和目标名生成辅助函数，改 `_target_video()` 使用双语命名。
- 修改 `config/config.example.toml`：同步默认模板说明为双语命名规范。
- 修改 `docs/architecture.md`：同步媒体命名规范。

不修改前端，不新增依赖，不新增后端 API。

## Task 1: 用失败测试锁定双语电影命名

**Files:**
- Modify: `backend/tests/test_rename.py`

- [ ] **Step 1: 写失败测试**

在 `RenameTest` 中追加：

```python
    def test_preview_uses_movie_nfo_bilingual_name_and_preserves_extension(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Movies" / "Old Name" / "old.name.mp4"
            movie_nfo = video.parent / "movie.nfo"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            movie_nfo.write_text(
                """
<movie>
  <title>沙丘</title>
  <originaltitle>Dune</originaltitle>
  <year>2021</year>
</movie>
""".strip(),
                encoding="utf-8",
            )
            item = MediaItem("movie", "Old Name", str(video), "Movies", str(root / "Movies"))

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "Movies" / "Dune - 沙丘 (2021)" / "Dune - 沙丘 (2021).mp4", targets)
        self.assertIn(root / "Movies" / "Dune - 沙丘 (2021)" / "movie.nfo", targets)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_rename.RenameTest.test_preview_uses_movie_nfo_bilingual_name_and_preserves_extension
```

Expected: 失败，目标仍是 `Old Name/Old Name.mp4` 或不包含 `Dune - 沙丘 (2021)`。

## Task 2: 用失败测试锁定双语剧集命名和 SxxExx

**Files:**
- Modify: `backend/tests/test_rename.py`

- [ ] **Step 1: 写失败测试**

在 `RenameTest` 中追加：

```python
    def test_preview_uses_tvshow_nfo_bilingual_name_and_keeps_sxxexx(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "TV" / "Pantheon (2022)" / "Season 01" / "Pantheon - S01E03.mkv"
            episode_nfo = video.with_suffix(".nfo")
            tvshow_nfo = root / "TV" / "Pantheon (2022)" / "tvshow.nfo"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            episode_nfo.write_text("<episodedetails />", encoding="utf-8")
            tvshow_nfo.write_text(
                """
<tvshow>
  <title>万神殿</title>
  <originaltitle>Pantheon</originaltitle>
  <year>2022</year>
</tvshow>
""".strip(),
                encoding="utf-8",
            )
            item = MediaItem(
                "series",
                "Pantheon",
                str(video),
                "TV",
                str(root / "TV"),
                year=2022,
                season=1,
                episode=3,
            )

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "TV" / "Pantheon - 万神殿 (2022)" / "Season 01" / "Pantheon - 万神殿 - S01E03.mkv", targets)
        self.assertIn(root / "TV" / "Pantheon - 万神殿 (2022)" / "Season 01" / "Pantheon - 万神殿 - S01E03.nfo", targets)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_rename.RenameTest.test_preview_uses_tvshow_nfo_bilingual_name_and_keeps_sxxexx
```

Expected: 失败，目标目录仍是 `Pantheon/Season 01/...` 或缺少中文名/年份。

## Task 3: 用失败测试锁定退化规则

**Files:**
- Modify: `backend/tests/test_rename.py`

- [ ] **Step 1: 写“不重复相同标题”测试**

在 `RenameTest` 中追加：

```python
    def test_preview_does_not_duplicate_same_local_and_original_title(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Movies" / "Old" / "old.mkv"
            movie_nfo = video.parent / "movie.nfo"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            movie_nfo.write_text(
                """
<movie>
  <title>Dune</title>
  <originaltitle>Dune</originaltitle>
  <year>2021</year>
</movie>
""".strip(),
                encoding="utf-8",
            )
            item = MediaItem("movie", "Old", str(video), "Movies", str(root / "Movies"))

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "Movies" / "Dune (2021)" / "Dune (2021).mkv", targets)
```

- [ ] **Step 2: 写“缺失 NFO 回退”测试**

在 `RenameTest` 中追加：

```python
    def test_preview_falls_back_to_scanned_title_without_nfo(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Movies" / "Old" / "old.ts"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            item = MediaItem("movie", "Dune", str(video), "Movies", str(root / "Movies"), year=2021)

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "Movies" / "Dune (2021)" / "Dune (2021).ts", targets)
```

- [ ] **Step 3: 运行新增退化测试确认失败或现状不完整**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest \
  backend.tests.test_rename.RenameTest.test_preview_does_not_duplicate_same_local_and_original_title \
  backend.tests.test_rename.RenameTest.test_preview_falls_back_to_scanned_title_without_nfo
```

Expected: 第一个测试失败；第二个测试可能已通过。若第二个已通过，保留它作为回归测试。

## Task 4: 实现 NFO 标题读取和双语目标名

**Files:**
- Modify: `backend/src/media_manager/rename.py`

- [ ] **Step 1: 增加 XML import**

在文件顶部增加：

```python
import xml.etree.ElementTree as ET
```

- [ ] **Step 2: 在类型定义后增加 NFO 辅助函数**

在 `RenameApplyResult` 后追加：

```python
class RenameName(TypedDict):
    display: str
    year: int | None


def _target_name(item: MediaItem, nfo: Path) -> RenameName:
    title, original, year = _nfo_values(nfo)
    local_title = title or item.title
    original_title = original or ""
    display = _join_titles(original_title, local_title)
    return {"display": display, "year": year or item.year}


def _nfo_values(path: Path) -> tuple[str, str, int | None]:
    if not path.exists():
        return "", "", None
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return "", "", None
    title = (root.findtext("title") or "").strip()
    original = (root.findtext("originaltitle") or "").strip()
    year_text = (root.findtext("year") or "").strip()
    return title, original, int(year_text) if year_text.isdigit() else None


def _join_titles(original: str, local: str) -> str:
    if original and local and original != local:
        return f"{original} - {local}"
    return original or local


def _with_year(name: str, year: int | None) -> str:
    return f"{name} ({year})" if year else name
```

- [ ] **Step 3: 增加当前剧集目录辅助函数**

在 `_target_video()` 前追加：

```python
def _show_dir(item: MediaItem) -> Path:
    video = Path(item.path)
    library = Path(item.library_path)
    try:
        first = video.relative_to(library).parts[0]
    except (ValueError, IndexError):
        return video.parents[1]
    return library / first
```

- [ ] **Step 4: 修改 `_target_video()`**

把 `_target_video()` 替换为：

```python
def _target_video(item: MediaItem) -> Path:
    video = Path(item.path)
    library = Path(item.library_path)
    extension = video.suffix
    if item.kind == "movie":
        target = _target_name(item, video.parent / "movie.nfo")
        name = _with_year(target["display"], target["year"])
        return library / name / f"{name}{extension}"
    if item.kind == "series":
        season = item.season or 1
        episode = item.episode or 1
        target = _target_name(item, _show_dir(item) / "tvshow.nfo")
        show_name = _with_year(target["display"], target["year"])
        file_name = f'{target["display"]} - S{season:02d}E{episode:02d}'
        return library / show_name / f"Season {season:02d}" / f"{file_name}{extension}"
    return video
```

- [ ] **Step 5: 运行重命名测试确认通过**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_rename
```

Expected: `OK`。

- [ ] **Step 6: 提交后端实现**

```bash
git add backend/src/media_manager/rename.py backend/tests/test_rename.py
git commit -m "feat: use bilingual names for media rename"
```

## Task 5: 同步默认配置和架构文档

**Files:**
- Modify: `config/config.example.toml`
- Modify: `docs/architecture.md`

- [ ] **Step 1: 更新示例配置模板**

把 `config/config.example.toml` 的 organizer 模板改为：

```toml
[organizer.movie]
directory_template = "{original_title} - {title} ({year})"
file_template = "{original_title} - {title} ({year})"

[organizer.series]
show_template = "{original_title} - {title} ({year})"
season_template = "Season {season:02d}"
episode_template = "{original_title} - {title} - S{season:02d}E{episode:02d}"
```

- [ ] **Step 2: 更新架构文档命名说明**

在 `docs/architecture.md` 的 `Media Model` 后追加：

```md
## Rename Model

重命名预览和执行采用 NFO 优先的双语命名：

- 电影：`英文名 - 中文名 (年份)/英文名 - 中文名 (年份).原扩展名`
- 剧集：`英文名 - 中文名 (年份)/Season 01/英文名 - 中文名 - S01E03.原扩展名`

如果 NFO 缺失或只有一个标题，则退回当前扫描标题；如果中英文标题相同，不重复拼接。视频扩展名继承原文件扩展名，不固定为 `.mkv`。
```

- [ ] **Step 3: 运行文档空白检查**

Run:

```bash
git diff --check
```

Expected: 退出码 0。

- [ ] **Step 4: 提交文档和配置**

```bash
git add config/config.example.toml docs/architecture.md
git commit -m "docs: document bilingual rename templates"
```

## Task 6: 全量验证和烟测

**Files:**
- Verify only

- [ ] **Step 1: 后端测试**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
```

Expected: 所有测试 `OK`。

- [ ] **Step 2: 前端构建**

Run:

```bash
cd frontend && npm run build
```

Expected: `tsc --noEmit && vite build` 退出码为 0。

- [ ] **Step 3: 空白和密钥检查**

Run:

```bash
git diff --check
rg -n 'api_key\s*=\s*"[A-Za-z0-9]{20,}"|api_key_env\s*=\s*"[A-Za-z0-9]{20,}"' . -g '!frontend/node_modules/**' -g '!frontend/dist/**' -g '!.venv/**'
```

Expected: `git diff --check` 退出码 0；`rg` 无命中。

- [ ] **Step 4: 本地 Pantheon 预览烟测**

若已有服务在 `127.0.0.1:8000`，复用它；否则启动：

```bash
MEDIA_MANAGER_STATIC_DIR=frontend/dist MEDIA_MANAGER_HOST=127.0.0.1 MEDIA_MANAGER_PORT=8000 PYTHONPATH=backend/src .venv/bin/python -m media_manager.server
```

查找 Pantheon 条目：

```bash
curl -fsS http://127.0.0.1:8000/api/media | .venv/bin/python -m json.tool
```

对 Pantheon 条目调用重命名预览：

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/media/<pantheon-id>/rename/preview | .venv/bin/python -m json.tool
```

Expected: 目标包含：

```text
Pantheon - 万神殿 (2022)/Season 01/Pantheon - 万神殿 - S01E03.<原扩展名>
```

不要在烟测中调用 `/rename/apply`。

## 自检

- spec 的电影、剧集、扩展名、退化规则和安全规则均有任务覆盖。
- 所有生产代码变化都有失败测试先行。
- 不新增前端改动、不新增依赖、不新增 API。
- 示例配置只同步规范，不引入模板解析器。

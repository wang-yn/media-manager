# 媒体库问题筛选与批量操作 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在媒体库详情中筛选缺少元数据、缺少字幕或命名不规范的内容，并通过前端引导队列分别完成批量刮削、批量字幕和批量重命名。

**Architecture:** 后端继续同步扫描文件系统，在现有媒体列表响应中增加媒体级元数据和重命名状态，并暴露已有整剧重命名预览函数。前端在 `App.tsx` 内维护临时筛选、选择、逐项确认队列和结果汇总，复用现有元数据、字幕及重命名弹窗，不增加后台任务、持久化状态或新依赖。

**Tech Stack:** Python 3.11、FastAPI、`unittest`、React 19、TypeScript 5、Vite 7、原生 CSS。

---

## 文件结构

- 修改 `backend/src/media_manager/media.py`：计算媒体级 `has_metadata` 状态。
- 修改 `backend/src/media_manager/server.py`：派生 `rename_needed`，增加整剧重命名预览 API。
- 修改 `backend/tests/test_media.py`：覆盖电影和剧集媒体级元数据状态。
- 修改 `backend/tests/test_server.py`：覆盖列表重命名状态、整剧预览、冲突和无副作用。
- 修改 `frontend/src/App.tsx`：增加筛选、选择、引导队列、批量重命名预览和结果汇总。
- 修改 `frontend/src/style.css`：增加筛选栏、复选框、批量工具栏、进度和汇总样式。

不创建新的业务模块，不增加前端测试框架或状态管理库。

### Task 1: 增加媒体级元数据状态

**Files:**
- Modify: `backend/src/media_manager/media.py:33-58,180-184`
- Test: `backend/tests/test_media.py:16-70`

- [ ] **Step 1: 写失败测试，区分媒体级元数据和单集 NFO**

在 `ScanLibrariesTest` 中给现有扫描测试补充缺失状态断言：

```python
self.assertFalse(items[0].has_metadata)
self.assertFalse(items[1].has_metadata)
```

再增加完整测试：

```python
def test_marks_movie_and_series_media_metadata(self) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        movie = root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
        episode = root / "tv" / "Pantheon (2022)" / "Season 01" / "Pantheon - S01E03.mkv"
        movie.parent.mkdir(parents=True)
        episode.parent.mkdir(parents=True)
        movie.write_text("", encoding="utf-8")
        episode.write_text("", encoding="utf-8")
        (movie.parent / "movie.nfo").write_text("<movie />", encoding="utf-8")
        (episode.parents[1] / "tvshow.nfo").write_text("<tvshow />", encoding="utf-8")

        items = scan_libraries(
            [
                Library("Movies", "movie", root / "movies"),
                Library("TV", "series", root / "tv"),
            ]
        )

    self.assertTrue(items[0].has_metadata)
    self.assertTrue(items[1].has_metadata)
    self.assertTrue(items[0].has_nfo)
    self.assertFalse(items[1].has_nfo)
    self.assertTrue(items[0].to_dict()["has_metadata"])
    self.assertTrue(items[1].to_dict()["has_metadata"])
```

- [ ] **Step 2: 运行媒体扫描测试，确认新断言失败**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_media.py'
```

Expected: FAIL，`MediaItem` 没有 `has_metadata` 属性。

- [ ] **Step 3: 在 `MediaItem` 中实现媒体级状态**

在 `has_nfo` 后增加字段：

```python
has_metadata: bool = False
```

在 `__post_init__()` 末尾增加：

```python
metadata_path = _metadata_path(self)
object.__setattr__(self, "has_metadata", bool(metadata_path and metadata_path.exists()))
```

在 `_nfo_path()` 后增加媒体级路径函数：

```python
def _metadata_path(item: MediaItem) -> Path | None:
    video = Path(item.path)
    if item.kind == "movie":
        return video.parent / "movie.nfo"
    if item.kind != "series":
        return None
    library = Path(item.library_path)
    try:
        show_name = video.relative_to(library).parts[0]
    except (ValueError, IndexError):
        return video.parents[1] / "tvshow.nfo"
    return library / show_name / "tvshow.nfo"
```

不要修改 `nfo_path` 和 `has_nfo` 的现有语义。`to_dict()` 会自动序列化新增布尔字段，包括 `False`。

- [ ] **Step 4: 运行媒体扫描测试，确认通过**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_media.py'
```

Expected: 全部测试通过，输出 `OK`。

- [ ] **Step 5: 提交媒体级元数据状态**

```bash
git add backend/src/media_manager/media.py backend/tests/test_media.py
git commit -m "feat: expose media metadata status"
```

### Task 2: 增加重命名状态和整剧预览 API

**Files:**
- Modify: `backend/src/media_manager/server.py:15-16,87-117,180-220`
- Test: `backend/tests/test_server.py:13-55,402-450`

- [ ] **Step 1: 写失败测试，锁定 `/api/media` 状态字段**

在 `ServerTest` 中增加：

```python
def test_media_reports_metadata_and_rename_status(self) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        media_root = root / "media"
        config_path = root / "config.toml"
        standard = media_root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
        irregular = media_root / "movies" / "Arrival (2016)" / "arrival.mkv"
        standard.parent.mkdir(parents=True)
        irregular.parent.mkdir(parents=True)
        standard.write_text("", encoding="utf-8")
        irregular.write_text("", encoding="utf-8")
        (standard.parent / "movie.nfo").write_text("<movie />", encoding="utf-8")
        config_path.write_text(
            f'''[paths]
media_dir = "{media_root}"

[[libraries]]
name = "Movies"
kind = "movie"
path = "{media_root / 'movies'}"
''',
            encoding="utf-8",
        )
        os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
        from media_manager.server import create_app

        response = TestClient(create_app()).get("/api/media")
        by_path = {item["path"]: item for item in response.json()["items"]}

    self.assertEqual(response.status_code, 200)
    self.assertTrue(by_path[str(standard)]["has_metadata"])
    self.assertFalse(by_path[str(standard)]["rename_needed"])
    self.assertFalse(by_path[str(irregular)]["has_metadata"])
    self.assertTrue(by_path[str(irregular)]["rename_needed"])
```

- [ ] **Step 2: 写失败测试，锁定整剧预览无文件修改**

增加：

```python
def test_batch_rename_series_previews_without_moving_files(self) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        media_root = root / "media"
        config_path = root / "config.toml"
        show = media_root / "tv" / "Pantheon (2022)"
        first = show / "Season 01" / "Pantheon - S01E03.mkv"
        second = show / "Season 02" / "Pantheon - S02E01.mp4"
        first.parent.mkdir(parents=True)
        second.parent.mkdir(parents=True)
        first.write_text("first", encoding="utf-8")
        second.write_text("second", encoding="utf-8")
        (show / "tvshow.nfo").write_text(
            "<tvshow><title>万神殿</title><originaltitle>Pantheon</originaltitle><year>2022</year></tvshow>",
            encoding="utf-8",
        )
        config_path.write_text(
            f'''[paths]
media_dir = "{media_root}"

[[libraries]]
name = "TV"
kind = "series"
path = "{media_root / 'tv'}"
''',
            encoding="utf-8",
        )
        os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
        from media_manager.server import create_app

        client = TestClient(create_app())
        item = next(item for item in client.get("/api/media").json()["items"] if item["path"] == str(first))
        response = client.post(f"/api/media/{item['id']}/rename/batch/preview")
        renamed = media_root / "tv" / "Pantheon - 万神殿 (2022)"

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["can_apply"])
        self.assertGreaterEqual(len(response.json()["changes"]), 3)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertFalse(renamed.exists())
```

- [ ] **Step 3: 写失败测试，锁定整剧冲突和电影拒绝行为**

增加整剧冲突测试：

```python
def test_batch_rename_series_preview_reports_conflict(self) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        media_root = root / "media"
        config_path = root / "config.toml"
        show = media_root / "tv" / "Pantheon (2022)"
        source = show / "Season 01" / "Pantheon - S01E03.mkv"
        target = media_root / "tv" / "Pantheon - 万神殿 (2022)" / "Season 01" / "Pantheon - 万神殿 - S01E03.mkv"
        source.parent.mkdir(parents=True)
        target.parent.mkdir(parents=True)
        source.write_text("source", encoding="utf-8")
        target.write_text("existing", encoding="utf-8")
        (show / "tvshow.nfo").write_text(
            "<tvshow><title>万神殿</title><originaltitle>Pantheon</originaltitle><year>2022</year></tvshow>",
            encoding="utf-8",
        )
        config_path.write_text(
            f'''[paths]
media_dir = "{media_root}"

[[libraries]]
name = "TV"
kind = "series"
path = "{media_root / 'tv'}"
''',
            encoding="utf-8",
        )
        os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
        from media_manager.server import create_app

        client = TestClient(create_app())
        item = next(item for item in client.get("/api/media").json()["items"] if item["path"] == str(source))
        response = client.post(f"/api/media/{item['id']}/rename/batch/preview")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["can_apply"])
        self.assertIn("target_exists", response.json()["conflicts"])
        self.assertEqual(source.read_text(encoding="utf-8"), "source")
        self.assertEqual(target.read_text(encoding="utf-8"), "existing")
```

增加电影拒绝测试：

```python
def test_batch_rename_preview_rejects_movie_item(self) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        media_root = root / "media"
        config_path = root / "config.toml"
        movie = media_root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
        movie.parent.mkdir(parents=True)
        movie.write_text("", encoding="utf-8")
        config_path.write_text(
            f'''[paths]
media_dir = "{media_root}"

[[libraries]]
name = "Movies"
kind = "movie"
path = "{media_root / 'movies'}"
''',
            encoding="utf-8",
        )
        os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
        from media_manager.server import create_app

        client = TestClient(create_app())
        movie_id = client.get("/api/media").json()["items"][0]["id"]
        response = client.post(f"/api/media/{movie_id}/rename/batch/preview")

    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json()["error"]["code"], "unsupported_batch_rename_target")
```

- [ ] **Step 4: 运行服务端测试，确认新行为尚未实现**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_server.py'
```

Expected: FAIL，媒体列表缺少 `rename_needed`，整剧预览端点返回非 200。

- [ ] **Step 5: 派生 `rename_needed` 并暴露整剧预览**

更新导入：

```python
from .rename import apply_batch_rename, apply_rename, preview_batch_rename, preview_rename
```

修改媒体列表端点：

```python
@app.get("/api/media")
def media() -> dict[str, object]:
    items = [_media_dict(item) for item in _scan(app)]
    return {"count": len(items), "items": items}
```

在 `_scan()` 后增加：

```python
def _media_dict(item: MediaItem) -> dict[str, object]:
    data = item.to_dict()
    preview = preview_rename(item)
    data["rename_needed"] = any(
        Path(change["from"]).resolve() != Path(change["to"]).resolve()
        for change in preview["changes"]
    )
    return data
```

在现有 `rename/batch` 端点前增加：

```python
@app.post("/api/media/{media_id}/rename/batch/preview")
def rename_batch_preview(media_id: str) -> dict[str, object]:
    item = _find_media(app, media_id)
    if item.kind != "series":
        raise AppError(
            "unsupported_batch_rename_target",
            "批量重命名预览只支持剧集",
            item.kind,
            item.path,
        )
    return preview_batch_rename(_series_items(app, item))
```

预览端点只调用 `preview_batch_rename()`，不得调用 `apply_batch_rename()`。

- [ ] **Step 6: 运行服务端测试，确认通过**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_server.py'
```

Expected: 全部测试通过，输出 `OK`。

- [ ] **Step 7: 运行后端全量测试**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
```

Expected: 全部测试通过，输出 `OK`。

- [ ] **Step 8: 提交后端问题状态和预览 API**

```bash
git add backend/src/media_manager/server.py backend/tests/test_server.py
git commit -m "feat: expose media rename status"
```

### Task 3: 增加问题筛选和整部剧选择

**Files:**
- Modify: `frontend/src/App.tsx:15-130,590-850,1180-1380`
- Modify: `frontend/src/style.css:15-35,130-230`

- [ ] **Step 1: 扩展前端媒体和剧集状态类型**

在 `MediaItem` 中增加：

```typescript
has_metadata: boolean;
rename_needed: boolean;
```

增加问题筛选和批量目标类型：

```typescript
type IssueFilter = "missing-metadata" | "missing-subtitles" | "rename-needed";

type BatchTarget = {
  key: string;
  item: MediaItem;
  items: MediaItem[];
};
```

在 `SeriesSummary` 中增加：

```typescript
hasMetadata: boolean;
renameNeeded: boolean;
missingSubtitles: number;
```

- [ ] **Step 2: 聚合整部剧的问题状态**

在 `groupSeriesShows()` 创建剧集汇总时加入：

```typescript
hasMetadata: item.has_metadata,
renameNeeded: item.rename_needed,
missingSubtitles: (item.subtitles ?? []).length === 0 ? 1 : 0,
```

已有剧集分支同步更新：

```typescript
current.hasMetadata = current.hasMetadata || item.has_metadata;
current.renameNeeded = current.renameNeeded || item.rename_needed;
current.missingSubtitles += (item.subtitles ?? []).length === 0 ? 1 : 0;
```

增加 OR 筛选函数：

```typescript
function matchesIssues(filters: IssueFilter[], hasMetadata: boolean, missingSubtitles: boolean, renameNeeded: boolean) {
  if (filters.length === 0) {
    return true;
  }
  return filters.some((filter) => {
    if (filter === "missing-metadata") {
      return !hasMetadata;
    }
    if (filter === "missing-subtitles") {
      return missingSubtitles;
    }
    return renameNeeded;
  });
}

function mediaMatchesIssues(item: MediaItem, filters: IssueFilter[]) {
  return matchesIssues(filters, item.has_metadata, (item.subtitles ?? []).length === 0, item.rename_needed);
}

function seriesMatchesIssues(show: SeriesSummary, filters: IssueFilter[]) {
  return matchesIssues(filters, show.hasMetadata, show.missingSubtitles > 0, show.renameNeeded);
}
```

- [ ] **Step 3: 在媒体库详情中维护筛选和选择**

在 `LibraryDetailView` 中增加状态：

```typescript
const [issueFilters, setIssueFilters] = useState<IssueFilter[]>([]);
const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
```

媒体库变化时清空状态：

```typescript
useEffect(() => {
  setIssueFilters([]);
  setSelectedKeys([]);
  setSelectedSeriesKey(null);
}, [library?.key]);
```

在确认 `library` 存在后计算可见目标：

```typescript
const series = library.kind === "series" ? groupSeriesShows(items) : [];
const visibleSeries = series.filter((show) => seriesMatchesIssues(show, issueFilters));
const visibleItems = library.kind === "movie" ? items.filter((item) => mediaMatchesIssues(item, issueFilters)) : items;
const visibleTargets: BatchTarget[] =
  library.kind === "series"
    ? visibleSeries.map((show) => ({ key: show.key, item: show.representative, items: show.items }))
    : visibleItems.map((item) => ({ key: item.id, item, items: [item] }));
const selectedTargets = visibleTargets.filter((target) => selectedKeys.includes(target.key));
```

切换筛选时清空选择：

```typescript
function toggleIssueFilter(filter: IssueFilter) {
  setIssueFilters((current) => (current.includes(filter) ? current.filter((value) => value !== filter) : [...current, filter]));
  setSelectedKeys([]);
}
```

- [ ] **Step 4: 增加筛选栏和选择栏组件**

只在电影一级列表或剧集一级列表渲染，不在 `selectedSeries` 单集详情中渲染：

```tsx
<IssueFilterBar filters={issueFilters} onToggle={toggleIssueFilter} />
<div className="batch-toolbar">
  <span>已选择 {selectedTargets.length} 项</span>
  <button type="button" className="link-button" onClick={() => setSelectedKeys(visibleTargets.map((target) => target.key))} disabled={visibleTargets.length === 0}>
    全选当前结果
  </button>
  <button type="button" className="link-button" onClick={() => setSelectedKeys([])} disabled={selectedKeys.length === 0}>
    清空选择
  </button>
</div>
```

增加组件：

```tsx
function IssueFilterBar({ filters, onToggle }: { filters: IssueFilter[]; onToggle: (filter: IssueFilter) => void }) {
  const options: Array<{ value: IssueFilter; label: string }> = [
    { value: "missing-metadata", label: "缺少元数据" },
    { value: "missing-subtitles", label: "缺少字幕" },
    { value: "rename-needed", label: "命名不规范" },
  ];
  return (
    <div className="issue-filters" aria-label="问题筛选">
      {options.map((option) => (
        <label key={option.value}>
          <input type="checkbox" checked={filters.includes(option.value)} onChange={() => onToggle(option.value)} />
          {option.label}
        </label>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: 给电影和剧集一级表格增加复选框**

为 `SeriesTable` 增加必填的 `selectedKeys`、`onToggle` 属性。为 `MediaTable` 增加可选属性：

```typescript
selectedKeys?: string[];
onToggle?: (key: string) => void;
```

电影一级列表传入这两个属性和 `visibleItems`；单集详情继续传入 `selectedSeries.items`，不传选择属性：

```tsx
<MediaTable
  items={selectedSeries ? selectedSeries.items : visibleItems}
  busy={busy}
  showMetadata={library.kind !== "series"}
  selectedKeys={selectedSeries ? undefined : selectedKeys}
  onToggle={selectedSeries ? undefined : toggleSelectedKey}
  onSearch={onSearch}
  onRename={onRename}
  onSearchSubtitle={onSearchSubtitle}
  onShowFiles={onShowFiles}
/>
```

剧集一级列表传入 `visibleSeries`、`selectedKeys` 和 `toggleSelectedKey`：

```tsx
<SeriesTable
  series={visibleSeries}
  busy={busy}
  selectedKeys={selectedKeys}
  onToggle={toggleSelectedKey}
  onSearch={onSearch}
  onOpen={setSelectedSeriesKey}
  onDelete={onDeleteSeries}
  onShowFiles={onShowFiles}
/>
```

增加选择切换函数：

```typescript
function toggleSelectedKey(key: string) {
  setSelectedKeys((current) => (current.includes(key) ? current.filter((value) => value !== key) : [...current, key]));
}
```

`MediaTable` 使用以下条件决定是否增加选择列：

```typescript
const selectable = Boolean(selectedKeys && onToggle);
```

在可选择表格的表头最前增加空标题，在每行最前增加：

```tsx
<td className="selection-cell">
  <input
    type="checkbox"
    aria-label={`选择 ${mediaTitle(item)}`}
    checked={selectedKeys.includes(item.id)}
    onChange={() => onToggle(item.id)}
  />
</td>
```

剧集使用 `show.key` 和 `mediaTitle(show)`。电影空列表行使用 `colSpan={selectable ? 9 : 8}`；剧集一级列表固定使用 `colSpan={9}`。单集详情表不增加选择列。

- [ ] **Step 6: 增加最小样式并构建**

在 `style.css` 增加：

```css
input[type="checkbox"] {
  width: 18px;
  min-width: 18px;
  height: 18px;
  min-height: 18px;
  accent-color: #1f6f64;
}

.issue-filters,
.batch-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.issue-filters label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.selection-cell {
  width: 42px;
}
```

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript 检查和 Vite 构建通过，输出 `✓ built`。

- [ ] **Step 7: 提交问题筛选和选择**

```bash
git add frontend/src/App.tsx frontend/src/style.css
git commit -m "feat: filter and select media issues"
```

### Task 4: 增加元数据和字幕引导队列

**Files:**
- Modify: `frontend/src/App.tsx:35-75,130-330,420-470,590-650,1000-1140`
- Modify: `frontend/src/style.css:230-320`

- [ ] **Step 1: 定义队列和结果类型**

在对话框类型后增加：

```typescript
type GuidedBatchKind = "metadata" | "subtitle";

type BatchResult = {
  label: string;
  status: "success" | "failed" | "skipped";
  error?: string;
};

type GuidedBatch = {
  kind: GuidedBatchKind;
  items: MediaItem[];
  index: number;
  results: BatchResult[];
};

type BatchSummary = {
  title: string;
  results: BatchResult[];
};
```

在 `App` 中增加：

```typescript
const [guidedBatch, setGuidedBatch] = useState<GuidedBatch | null>(null);
const [batchSummary, setBatchSummary] = useState<BatchSummary | null>(null);
```

- [ ] **Step 2: 增加启动和推进队列函数**

增加：

```typescript
function startGuidedBatch(kind: GuidedBatchKind, items: MediaItem[], skipped: MediaItem[]) {
  const results = skipped.map((item) => ({ label: guidedBatchLabel(kind, item), status: "skipped" as const }));
  if (items.length === 0) {
    setBatchSummary({ title: kind === "metadata" ? "批量刮削结果" : "批量字幕结果", results });
    return;
  }
  setGuidedBatch({ kind, items, index: 0, results });
  if (kind === "metadata") {
    openMetadataDialog(items[0]);
  } else {
    openSubtitleDialog(items[0]);
  }
}

function startMetadataBatch(targets: BatchTarget[]) {
  const items = targets.filter((target) => !target.item.has_metadata).map((target) => target.item);
  const skipped = targets.filter((target) => target.item.has_metadata).map((target) => target.item);
  startGuidedBatch("metadata", items, skipped);
}

function startSubtitleBatch(targets: BatchTarget[]) {
  const allItems = targets.flatMap((target) => target.items).sort(compareEpisodes);
  const items = allItems.filter((item) => (item.subtitles ?? []).length === 0);
  const skipped = allItems.filter((item) => (item.subtitles ?? []).length > 0);
  startGuidedBatch("subtitle", items, skipped);
}
```

增加稳定排序：

```typescript
function compareEpisodes(left: MediaItem, right: MediaItem) {
  return (left.season ?? 0) - (right.season ?? 0) || (left.episode ?? 0) - (right.episode ?? 0) || left.path.localeCompare(right.path);
}

function guidedBatchLabel(kind: GuidedBatchKind, item: MediaItem) {
  if (kind === "subtitle" && item.season !== undefined && item.episode !== undefined) {
    return `${mediaTitle(item)} - S${pad(item.season)}E${pad(item.episode)}`;
  }
  return mediaTitle(item);
}
```

- [ ] **Step 3: 成功后推进，结束后刷新并汇总**

增加：

```typescript
async function advanceGuidedBatch(status: "success" | "skipped") {
  if (!guidedBatch) {
    return;
  }
  const current = guidedBatch.items[guidedBatch.index];
  const results = [...guidedBatch.results, { label: guidedBatchLabel(guidedBatch.kind, current), status }];
  const nextIndex = guidedBatch.index + 1;
  if (nextIndex < guidedBatch.items.length) {
    const next = guidedBatch.items[nextIndex];
    setGuidedBatch({ ...guidedBatch, index: nextIndex, results });
    guidedBatch.kind === "metadata" ? openMetadataDialog(next) : openSubtitleDialog(next);
    return;
  }
  setGuidedBatch(null);
  setMetadataDialog(null);
  setSubtitleDialog(null);
  setBatchSummary({ title: guidedBatch.kind === "metadata" ? "批量刮削结果" : "批量字幕结果", results });
  await refreshContent();
}
```

修改 `applySelectedMetadata()` 和 `downloadSelectedSubtitle()` 的成功分支：

```typescript
if (guidedBatch?.kind === "metadata") {
  await advanceGuidedBatch("success");
} else {
  setMetadataDialog(null);
  await refreshContent();
}
```

字幕分支使用 `guidedBatch?.kind === "subtitle"`，否则保持原有单项行为。

- [ ] **Step 4: 增加跳过和取消语义**

增加：

```typescript
async function skipGuidedBatch() {
  await advanceGuidedBatch("skipped");
}

async function cancelGuidedBatch() {
  if (!guidedBatch) {
    setMetadataDialog(null);
    setSubtitleDialog(null);
    return;
  }
  const currentError = guidedBatch.kind === "metadata" ? metadataDialog?.error : subtitleDialog?.error;
  const remaining = guidedBatch.items.slice(guidedBatch.index);
  const results = [
    ...guidedBatch.results,
    ...remaining.map((item, index) => ({
      label: guidedBatchLabel(guidedBatch.kind, item),
      status: index === 0 && currentError ? ("failed" as const) : ("skipped" as const),
      error: index === 0 ? currentError : undefined,
    })),
  ];
  setGuidedBatch(null);
  setMetadataDialog(null);
  setSubtitleDialog(null);
  setBatchSummary({ title: guidedBatch.kind === "metadata" ? "批量刮削结果" : "批量字幕结果", results });
  await refreshContent();
}
```

失败时继续使用现有弹窗错误状态；不自动推进，不自动重试。

- [ ] **Step 5: 在批量工具栏接入两个入口**

给 `LibraryDetailView` 增加并传递：

```typescript
onBatchMetadata: (targets: BatchTarget[]) => void;
onBatchSubtitles: (targets: BatchTarget[]) => void;
```

在选择栏中增加：

```tsx
<button type="button" onClick={() => onBatchMetadata(selectedTargets)} disabled={selectedTargets.length === 0}>
  批量刮削
</button>
<button type="button" onClick={() => onBatchSubtitles(selectedTargets)} disabled={selectedTargets.length === 0}>
  批量字幕
</button>
```

`App` 传入 `startMetadataBatch` 和 `startSubtitleBatch`。

- [ ] **Step 6: 扩展现有弹窗显示进度、跳过和取消**

给 `MetadataDialogView` 和 `SubtitleDialogView` 增加可选属性：

```typescript
progress?: { current: number; total: number };
onSkip?: () => void;
```

标题区域显示：

```tsx
{progress ? <span className="batch-progress">{progress.current} / {progress.total}</span> : null}
```

按钮区域在批量模式增加：

```tsx
{onSkip ? (
  <button type="button" className="link-button" onClick={onSkip} disabled={searching || applying}>
    跳过
  </button>
) : null}
<button type="button" className="link-button" onClick={onClose}>
  {progress ? "取消批量" : "取消"}
</button>
```

字幕弹窗把 `applying` 替换为现有 `downloading`。`App` 在队列存在时传入进度、`skipGuidedBatch` 和 `cancelGuidedBatch`；右上角 `X` 同样使用 `cancelGuidedBatch`。

- [ ] **Step 7: 增加结果汇总弹窗**

增加 `BatchSummaryDialog`，统计并显示：

```tsx
function BatchSummaryDialog({ summary, onClose }: { summary: BatchSummary; onClose: () => void }) {
  const count = (status: BatchResult["status"]) => summary.results.filter((result) => result.status === status).length;
  const failures = summary.results.filter((result) => result.status === "failed");
  return (
    <div className="dialog-backdrop">
      <section className="dialog" role="dialog" aria-modal="true" aria-label={summary.title}>
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭">X</button>
        <h2>{summary.title}</h2>
        <div className="batch-counts">
          <span className="good">成功 {count("success")}</span>
          <span className="error">失败 {count("failed")}</span>
          <span>跳过 {count("skipped")}</span>
        </div>
        {failures.map((result, index) => <p key={`${result.label}:${index}`} className="notice error">{result.label}：{result.error}</p>)}
        <div className="dialog-actions"><button type="button" onClick={onClose}>确定</button></div>
      </section>
    </div>
  );
}
```

在 `App` 返回内容末尾渲染 `batchSummary`。

- [ ] **Step 8: 增加队列样式并构建**

在 `style.css` 增加：

```css
.batch-progress {
  color: #52616b;
  font-size: 13px;
}

.batch-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 14px 0;
}
```

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript 检查和 Vite 构建通过，输出 `✓ built`。

- [ ] **Step 9: 提交元数据和字幕队列**

```bash
git add frontend/src/App.tsx frontend/src/style.css
git commit -m "feat: guide batch metadata and subtitles"
```

### Task 5: 增加批量重命名汇总预览和执行

**Files:**
- Modify: `frontend/src/App.tsx:65-90,250-380,420-470,600-640,870-980`
- Modify: `frontend/src/style.css:200-320`

- [ ] **Step 1: 定义批量重命名弹窗状态**

增加：

```typescript
type BatchRenameEntry = {
  target: BatchTarget;
  preview?: RenamePreview;
  error?: string;
};

type BatchRenameDialog = {
  entries: BatchRenameEntry[];
};
```

在 `App` 中增加：

```typescript
const [batchRenameDialog, setBatchRenameDialog] = useState<BatchRenameDialog | null>(null);
```

- [ ] **Step 2: 并行加载电影和整剧预览**

用以下函数替换当前直接执行整剧重命名的 `batchRenameSeries()`：

```typescript
async function openBatchRenameDialog(targets: BatchTarget[]) {
  setBusy("batch-rename-preview");
  const entries = await Promise.all(
    targets.map(async (target): Promise<BatchRenameEntry> => {
      const url = target.item.kind === "series"
        ? `/api/media/${target.item.id}/rename/batch/preview`
        : `/api/media/${target.item.id}/rename/preview`;
      try {
        return { target, preview: await request<RenamePreview>(url, { method: "POST" }) };
      } catch (err) {
        return { target, error: messageFrom(err) };
      }
    }),
  );
  setBatchRenameDialog({ entries });
  setBusy(null);
}
```

给 `LibraryDetailView` 增加 `onBatchRename`，批量工具栏调用 `onBatchRename(selectedTargets)`。

剧集详情页原有“批量重命名”按钮改为：

```tsx
onBatchRename([{ key: selectedSeries.key, item: selectedSeries.representative, items: selectedSeries.items }])
```

- [ ] **Step 3: 实现顺序执行和部分成功汇总**

增加：

```typescript
async function applyBatchRename(dialog: BatchRenameDialog) {
  setBusy("batch-rename-apply");
  const results: BatchResult[] = [];
  for (const entry of dialog.entries) {
    const label = mediaTitle(entry.target.item);
    if (entry.error) {
      results.push({ label, status: "failed", error: entry.error });
      continue;
    }
    if (!entry.preview?.can_apply) {
      results.push({ label, status: "failed", error: entry.preview?.conflicts.join(", ") || "重命名存在冲突" });
      continue;
    }
    if (!hasRenameChanges(entry.preview)) {
      results.push({ label, status: "skipped" });
      continue;
    }
    const url = entry.target.item.kind === "series"
      ? `/api/media/${entry.target.item.id}/rename/batch`
      : `/api/media/${entry.target.item.id}/rename/apply`;
    try {
      await request(url, { method: "POST" });
      results.push({ label, status: "success" });
    } catch (err) {
      results.push({ label, status: "failed", error: messageFrom(err) });
    }
  }
  setBusy(null);
  setBatchRenameDialog(null);
  setBatchSummary({ title: "批量重命名结果", results });
  await refreshContent();
}
```

该函数不回滚已成功条目，失败后继续处理剩余条目。

- [ ] **Step 4: 增加批量重命名汇总弹窗**

增加 `BatchRenameDialogView`：

```tsx
function BatchRenameDialogView({ dialog, busy, onApply, onClose }: {
  dialog: BatchRenameDialog;
  busy: string | null;
  onApply: (dialog: BatchRenameDialog) => void;
  onClose: () => void;
}) {
  const applying = busy === "batch-rename-apply";
  const executable = dialog.entries.some((entry) => entry.preview?.can_apply && hasRenameChanges(entry.preview));
  return (
    <div className="dialog-backdrop">
      <section className="dialog batch-rename-dialog" role="dialog" aria-modal="true" aria-label="批量重命名">
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭">X</button>
        <h2>批量重命名</h2>
        <div className="batch-rename-groups">
          {dialog.entries.map((entry) => {
            const changes = entry.preview ? renameChanges(entry.preview) : [];
            return (
              <section key={entry.target.key} className="batch-rename-group">
                <h3>{mediaTitle(entry.target.item)}</h3>
                {entry.error ? <p className="notice error">{entry.error}</p> : null}
                {entry.preview?.conflicts.length ? <p className="notice error">冲突：{entry.preview.conflicts.join(", ")}</p> : null}
                {entry.preview && changes.length === 0 ? <p>已经是规范名称，无需修改。</p> : null}
                {changes.map((change) => (
                  <RenameChangePreview key={`${change.from}:${change.to}`} change={change} libraryPath={entry.target.item.library_path} />
                ))}
              </section>
            );
          })}
        </div>
        <div className="dialog-actions">
          <button type="button" onClick={() => onApply(dialog)} disabled={!executable || applying}>{applying ? "重命名中" : "确定"}</button>
          <button type="button" className="link-button" onClick={onClose} disabled={applying}>取消</button>
        </div>
      </section>
    </div>
  );
}
```

在 `App` 中渲染该弹窗，`X` 和“取消”只丢弃预览，不修改文件。

- [ ] **Step 5: 删除旧的直接执行交互并统一入口**

删除：

- `batchRenameSeries()` 中的 `window.confirm` 和直接调用 `/rename/batch` 的逻辑。
- `LibraryDetailView` 的 `onBatchRenameSeries` 属性。

单项电影或单集的 `RenameDialogView` 保持不变。剧集详情页和多选工具栏统一调用 `openBatchRenameDialog()`。

- [ ] **Step 6: 增加批量重命名样式并构建**

在 `style.css` 增加：

```css
.batch-rename-dialog {
  width: min(920px, calc(100vw - 32px));
}

.batch-rename-groups {
  display: grid;
  gap: 14px;
  max-height: 60vh;
  overflow-y: auto;
}

.batch-rename-group {
  display: grid;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e4eaed;
}

.batch-rename-group h3 {
  margin: 0;
  font-size: 15px;
}
```

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript 检查和 Vite 构建通过，输出 `✓ built`。

- [ ] **Step 7: 提交批量重命名交互**

```bash
git add frontend/src/App.tsx frontend/src/style.css
git commit -m "feat: preview batch media renames"
```

### Task 6: 全量验证和手工验收

**Files:**
- Verify: `backend/tests/`
- Verify: `frontend/src/App.tsx`
- Verify: `frontend/src/style.css`
- Verify: `media/`

- [ ] **Step 1: 运行后端全量测试**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
```

Expected: 所有测试通过，输出 `OK`，没有失败或错误。

- [ ] **Step 2: 运行前端生产构建**

Run:

```bash
cd frontend && npm run build
```

Expected: `tsc --noEmit` 和 Vite 构建通过，输出 `✓ built`。

- [ ] **Step 3: 检查补丁格式和工作区**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: `git diff --check` 无输出；状态只包含实现过程中明确保留的改动，正常情况下工作区干净。

- [ ] **Step 4: 使用示例媒体完成浏览器验收**

从仓库根目录启动应用：

```bash
MEDIA_MANAGER_CONFIG=config/config.toml HTTP_PROXY=http://localhost:7890 HTTPS_PROXY=http://localhost:7890 PYTHONPATH=backend/src .venv/bin/python -m media_manager.server
```

Expected: 按当前 `config/config.toml` 监听 `http://localhost:8002`，首页和 `/api/health` 均可访问。随后验证：

1. 三个问题筛选可单选和组合，组合使用 OR 语义。
2. 修改筛选会清空选择，“全选当前结果”不选择隐藏项目。
3. 剧集一级列表只选择整部剧，批量字幕按季、集展开缺字幕单集。
4. 元数据和字幕弹窗显示进度，成功后进入下一项；跳过、取消和 `X` 行为符合 spec。
5. 当前项失败时错误保留在弹窗内，用户可以重试、跳过或取消。
6. 批量重命名先显示所有路径差异，规范名称、冲突和不可执行项目不会被修改。
7. 结果弹窗显示成功、失败和跳过数量；操作结束后列表状态刷新。

- [ ] **Step 5: 确认提交序列**

Run:

```bash
git log --oneline -6
```

Expected: 最新历史中包含以下五个实现提交；`git log` 按从新到旧显示：

```text
feat: preview batch media renames
feat: guide batch metadata and subtitles
feat: filter and select media issues
feat: expose media rename status
feat: expose media metadata status
```

如果验证中修复了实际缺陷，将相关文件加入一个独立提交，并在提交信息中描述该缺陷；不要修改已经完成的提交。

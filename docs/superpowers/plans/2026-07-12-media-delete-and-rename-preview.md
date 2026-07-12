# 媒体删除与重命名预览优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为电影列表增加整目录删除能力，并在批量重命名弹窗中隐藏修改前后文件名相同的文件明细。

**Architecture:** 继续复用现有媒体删除接口和 `_item_directory()`，只在删除入口补充禁止删除媒体库根目录的保护。前端复用剧集删除交互，并仅在批量重命名弹窗的展示层过滤同名文件；完整变更仍用于冲突检查和执行。

**Tech Stack:** Python 3.11、FastAPI、`unittest`、React 19、TypeScript 5、Vite 7、Playwright。

---

## 文件结构

- 修改 `backend/tests/test_server.py`：覆盖电影目录删除及媒体库根目录保护。
- 修改 `backend/src/media_manager/server.py`：让现有删除接口支持电影，并保留删除边界校验。
- 修改 `frontend/src/App.tsx`：复用删除处理、增加电影删除按钮、过滤批量重命名同名文件明细。

不创建新的业务模块，不修改重命名 API，不增加前端依赖。

### Task 1: 支持安全删除电影目录

**Files:**
- Modify: `backend/tests/test_server.py:315-355`
- Modify: `backend/src/media_manager/server.py:144-151`

- [ ] **Step 1: 将电影拒绝测试改为电影目录删除测试**

用以下测试替换 `test_delete_rejects_movie_item`：

```python
def test_delete_movie_removes_movie_directory(self) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        media_root = root / "media"
        config_path = root / "config.toml"
        movie_dir = media_root / "movies" / "Dune (2021)"
        movie = movie_dir / "Dune (2021).mkv"
        subtitle = movie_dir / "Dune (2021).zh.srt"
        nfo = movie_dir / "movie.nfo"
        movie_dir.mkdir(parents=True)
        movie.write_text("video", encoding="utf-8")
        subtitle.write_text("subtitle", encoding="utf-8")
        nfo.write_text("<movie />", encoding="utf-8")
        config_path.write_text(
            f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "Movies"
kind = "movie"
path = "{media_root / "movies"}"
""".strip()
            + "\n",
            encoding="utf-8",
        )
        os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
        from media_manager.server import create_app

        client = TestClient(create_app())
        media_id = client.get("/api/media").json()["items"][0]["id"]
        response = client.delete(f"/api/media/{media_id}")
        count_after_delete = client.get("/api/media").json()["count"]
        movie_dir_exists = movie_dir.exists()

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["deleted_path"], str(movie_dir))
    self.assertFalse(movie_dir_exists)
    self.assertEqual(count_after_delete, 0)
```

- [ ] **Step 2: 增加禁止删除媒体库根目录的测试**

在电影删除测试后增加：

```python
def test_delete_movie_rejects_library_root(self) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        media_root = root / "media"
        movies = media_root / "movies"
        config_path = root / "config.toml"
        movie = movies / "Loose.Movie.2024.mkv"
        movies.mkdir(parents=True)
        movie.write_text("video", encoding="utf-8")
        config_path.write_text(
            f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "Movies"
kind = "movie"
path = "{movies}"
""".strip()
            + "\n",
            encoding="utf-8",
        )
        os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
        from media_manager.server import create_app

        client = TestClient(create_app())
        media_id = client.get("/api/media").json()["items"][0]["id"]
        response = client.delete(f"/api/media/{media_id}")
        movies_exists = movies.exists()
        movie_exists = movie.exists()

    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json()["error"]["code"], "invalid_delete_target")
    self.assertTrue(movies_exists)
    self.assertTrue(movie_exists)
```

- [ ] **Step 3: 运行服务端测试，确认电影删除测试失败**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_server.py'
```

Expected: FAIL；电影删除返回 `400` 和 `unsupported_delete_target`，媒体库根目录保护测试尚未得到 `invalid_delete_target`。

- [ ] **Step 4: 让删除接口复用媒体目录解析并保护媒体库根目录**

将 `delete_media()` 改为：

```python
@app.delete("/api/media/{media_id}")
def delete_media(media_id: str) -> dict[str, str]:
    item = _find_media(app, media_id)
    path = _item_directory(item).resolve()
    library_root = Path(item.library_path).resolve()
    if path == library_root:
        raise AppError("invalid_delete_target", "不能删除媒体库根目录", str(library_root), item.path)
    try:
        shutil.rmtree(path)
    except OSError as exc:
        raise AppError("delete_failed", "删除媒体目录失败", str(exc), str(path), status=500) from exc
    return {"deleted_path": str(path)}
```

不要修改 `_series_directory()`；剧集仍通过 `_item_directory()` 进入原有整剧目录解析。

- [ ] **Step 5: 运行服务端测试，确认通过**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_server.py'
```

Expected: 全部测试通过，输出 `OK`。

- [ ] **Step 6: 提交电影目录删除后端**

```bash
git add backend/src/media_manager/server.py backend/tests/test_server.py
git commit -m "feat: delete movie directories"
```

### Task 2: 在电影列表复用删除交互

**Files:**
- Modify: `frontend/src/App.tsx:461-476,630-650,800-1165`

- [ ] **Step 1: 写电影删除按钮的失败验收脚本**

使用 `apply_patch` 创建 `/tmp/media-manager-playwright/movie-delete-check.cjs`：

```javascript
const { chromium } = require("/tmp/media-manager-playwright/node_modules/playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  let confirmation = "";
  let deleteRequests = 0;
  page.on("request", (request) => {
    if (request.method() === "DELETE") deleteRequests += 1;
  });
  page.on("dialog", async (dialog) => {
    confirmation = dialog.message();
    await dialog.dismiss();
  });

  try {
    await page.goto("http://localhost:8003", { waitUntil: "networkidle" });
    await page.locator(".library-card").filter({ hasText: "Movies" }).click();
    const row = page.locator(".media-table tbody tr").filter({ hasText: "Old Name" });
    await row.getByRole("button", { name: "删除", exact: true }).click();
    if (!confirmation.includes("确定删除电影目录 Old Name")) throw new Error(confirmation);
    if (!confirmation.includes("目录下所有文件")) throw new Error(confirmation);
    if (deleteRequests !== 0) throw new Error(`cancel sent ${deleteRequests} DELETE request(s)`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
```

- [ ] **Step 2: 运行验收脚本，确认电影行没有删除按钮**

Run:

```bash
LD_LIBRARY_PATH=/tmp/media-manager-browser-libs/usr/lib/x86_64-linux-gnu node /tmp/media-manager-playwright/movie-delete-check.cjs
```

Expected: FAIL；Playwright 找不到电影行中的“删除”按钮。

- [ ] **Step 3: 将剧集删除处理泛化为媒体删除**

把 `deleteSeries()` 改名并替换为：

```typescript
async function deleteMedia(item: MediaItem) {
  const path = item.kind === "series" ? seriesDirectoryPath(item) : dirname(item.path);
  const type = item.kind === "series" ? "剧集" : "电影";
  if (!window.confirm(`确定删除${type}目录 ${relativeLibraryPath(path, item.library_path)}？此操作会删除目录下所有文件。`)) {
    return;
  }
  const busyKey = `delete:${item.id}`;
  setBusy(busyKey);
  setError(null);
  try {
    await request<{ deleted_path: string }>(`/api/media/${item.id}`, { method: "DELETE" });
    await refreshContent();
  } catch (err) {
    setError(messageFrom(err));
  } finally {
    setBusy((current) => (current === busyKey ? null : current));
  }
}
```

在 `App` 调用 `LibraryDetailView` 时传入：

```tsx
onDeleteMedia={deleteMedia}
```

将 `LibraryDetailView` 的 `onDeleteSeries` 属性统一改名为：

```typescript
onDeleteMedia: (item: MediaItem) => void;
```

剧集表继续传入：

```tsx
onDelete={onDeleteMedia}
```

- [ ] **Step 4: 给电影表格和行组件传入删除处理**

调用 `MediaTable` 时增加：

```tsx
onDelete={onDeleteMedia}
```

在 `MediaTable` 参数类型中增加：

```typescript
onDelete: (item: MediaItem) => void;
```

创建 `Row` 时增加：

```tsx
onDelete={() => onDelete(item)}
```

在 `Row` 参数类型中增加：

```typescript
onDelete: () => void;
```

在电影行操作区末尾增加：

```tsx
<button type="button" className="danger-button" onClick={onDelete} disabled={busy === `delete:${item.id}`}>
  {busy === `delete:${item.id}` ? "删除中" : "删除"}
</button>
```

- [ ] **Step 5: 构建前端并重跑电影删除验收**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript 检查和 Vite 构建通过。

Run:

```bash
LD_LIBRARY_PATH=/tmp/media-manager-browser-libs/usr/lib/x86_64-linux-gnu node /tmp/media-manager-playwright/movie-delete-check.cjs
```

Expected: PASS；确认文案包含电影相对目录，取消后未发送 `DELETE` 请求。

- [ ] **Step 6: 删除临时脚本并提交电影删除交互**

```bash
rm /tmp/media-manager-playwright/movie-delete-check.cjs
git add frontend/src/App.tsx
git commit -m "feat: delete movies from library"
```

### Task 3: 隐藏批量重命名中的同名文件明细

**Files:**
- Modify: `frontend/src/App.tsx:1261-1302,1868-1874`

- [ ] **Step 1: 写仅目录变化的失败验收脚本**

使用 `apply_patch` 创建 `/tmp/media-manager-playwright/rename-preview-check.cjs`：

```javascript
const { chromium } = require("/tmp/media-manager-playwright/node_modules/playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.route("**/api/media/*/rename/batch/preview", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        can_apply: true,
        conflicts: [],
        changes: [
          {
            from: "/media/tv/Pantheon (2022)/tvshow.nfo",
            to: "/media/tv/Pantheon - 万神殿 (2022)/tvshow.nfo",
          },
        ],
      }),
    });
  });

  try {
    await page.goto("http://localhost:8003", { waitUntil: "networkidle" });
    await page.locator(".library-card").filter({ hasText: "TV" }).click();
    await page.getByLabel("选择 Pantheon (2022)", { exact: true }).check();
    await page.getByRole("button", { name: "批量重命名", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "批量重命名预览" });
    if ((await dialog.locator(".rename-change").count()) !== 0) throw new Error("same-name file detail is still visible");
    await dialog.getByText("仅调整目录位置。", { exact: true }).waitFor();
    if (await dialog.getByRole("button", { name: "确定", exact: true }).isDisabled()) throw new Error("path-only rename is not executable");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
```

- [ ] **Step 2: 运行验收脚本，确认同名记录仍显示**

Run:

```bash
LD_LIBRARY_PATH=/tmp/media-manager-browser-libs/usr/lib/x86_64-linux-gnu node /tmp/media-manager-playwright/rename-preview-check.cjs
```

Expected: FAIL；弹窗中仍有一条 `.rename-change`，且没有“仅调整目录位置。”提示。

- [ ] **Step 3: 增加只用于批量弹窗展示的过滤函数**

在 `renameChanges()` 后增加：

```typescript
function visibleBatchRenameChanges(preview: RenamePreview) {
  return renameChanges(preview).filter((change) => baseName(change.from) !== baseName(change.to));
}
```

不要修改 `renameChanges()`、`hasRenameChanges()`、`markDuplicateRenameTargets()` 或 `applyBatchRename()`，确保同名文件的目录迁移仍参与冲突检查和执行。

- [ ] **Step 4: 批量弹窗仅渲染可见变更**

在 `BatchRenameDialogView` 的条目渲染中改为：

```typescript
const changes = preview ? renameChanges(preview) : [];
const visibleChanges = preview ? visibleBatchRenameChanges(preview) : [];
```

保留原有“已经是规范名称”判断，并增加目录调整提示：

```tsx
{changes.length === 0 && preview.conflicts.length === 0 ? <p>已经是规范名称，无需修改。</p> : null}
{changes.length > 0 && visibleChanges.length === 0 ? <p>仅调整目录位置。</p> : null}
{visibleChanges.map((change) => (
  <RenameChangePreview key={`${change.from}:${change.to}`} change={change} libraryPath={entry.target.item.library_path} />
))}
```

- [ ] **Step 5: 构建前端并重跑批量预览验收**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript 检查和 Vite 构建通过。

Run:

```bash
LD_LIBRARY_PATH=/tmp/media-manager-browser-libs/usr/lib/x86_64-linux-gnu node /tmp/media-manager-playwright/rename-preview-check.cjs
```

Expected: PASS；同名明细不显示，出现“仅调整目录位置。”，确定按钮仍可点击。

- [ ] **Step 6: 删除临时脚本并提交预览优化**

```bash
rm /tmp/media-manager-playwright/rename-preview-check.cjs
git add frontend/src/App.tsx
git commit -m "fix: hide unchanged rename filenames"
```

### Task 4: 全量验证

**Files:**
- Verify only

- [ ] **Step 1: 运行后端全量测试**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
```

Expected: 全部测试通过，输出 `OK`。

- [ ] **Step 2: 运行前端生产构建**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript 检查和 Vite 构建通过。

- [ ] **Step 3: 检查差异和工作区**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: `git diff --check` 无输出；工作区无未提交文件。

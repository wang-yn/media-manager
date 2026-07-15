# 媒体库质量治理只读检查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加同步、只读的媒体库质量检查接口和前端结果弹窗。

**Architecture:** 后端把质量检查放在 `media.py`，复用现有视频扩展名、字幕扩展名、忽略目录和相对路径规则；`server.py` 只暴露薄的 `GET /api/audit`。前端在媒体库详情页增加“检查媒体库”入口，结果只保存在当前 React 会话内，并在浏览器端完成筛选和 CSV 导出。

**Tech Stack:** Python 3.11、FastAPI、`unittest`、React 19、TypeScript 5、Vite 7。

---

## 文件结构

- 修改 `backend/src/media_manager/media.py`：新增审计数据结构、审计规则和 `audit_libraries()`。
- 修改 `backend/tests/test_media.py`：覆盖所有后端质量检查规则。
- 修改 `backend/src/media_manager/server.py`：新增 `GET /api/audit`，并对媒体库根目录做接口级校验。
- 修改 `backend/tests/test_server.py`：覆盖审计接口响应和缺失媒体库错误。
- 修改 `frontend/src/App.tsx`：新增审计类型、状态、请求函数、结果弹窗、筛选和 CSV 导出。
- 修改 `frontend/src/style.css`：复用现有弹窗风格，增加审计结果表格和筛选样式。

不新增依赖，不新增数据库，不新增后台任务，不修改 `GET /api/media`。

### Task 1: 后端质量检查核心

**Files:**
- Modify: `backend/tests/test_media.py`
- Modify: `backend/src/media_manager/media.py`

- [ ] **Step 1: 写覆盖质量检查规则的失败测试**

修改 `backend/tests/test_media.py` 的 import：

```python
from media_manager.media import MediaItem, audit_libraries, scan_libraries
```

在 `ScanLibrariesTest` 内追加：

```python
    def test_audit_libraries_reports_quality_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movies = root / "movies"
            tv = root / "tv"

            (movies / "Empty").mkdir(parents=True)
            (movies / "Images Only").mkdir(parents=True)
            (movies / "Images Only" / "poster.jpg").write_bytes(b"poster")
            (movies / "Loose.Movie.2024.mkv").write_bytes(b"x")
            (movies / "Bad Movie").mkdir(parents=True)
            (movies / "Bad Movie" / "Bad Movie.mkv").write_bytes(b"x")
            (movies / "Orphans").mkdir(parents=True)
            (movies / "Orphans" / "lost.srt").write_text("subtitle", encoding="utf-8")
            (movies / ".@__thumb").mkdir(parents=True)
            (movies / ".@__thumb" / "ignored.srt").write_text("ignored", encoding="utf-8")
            ok_movie = movies / "沙丘 Dune (2021)" / "沙丘 Dune (2021).mkv"
            ok_movie.parent.mkdir(parents=True)
            ok_movie.write_bytes(b"")
            ok_movie.truncate(105 * 1024 * 1024)

            (tv / "Root.Show.S01E01.mkv").parent.mkdir(parents=True, exist_ok=True)
            (tv / "Root.Show.S01E01.mkv").write_bytes(b"x")
            missing_season = tv / "Pantheon (2022)" / "Pantheon - S01E03.mkv"
            missing_season.parent.mkdir(parents=True)
            missing_season.write_bytes(b"x")
            bad_season = tv / "Good Show (2024)" / "Season One" / "Good Show - S01E01.mkv"
            bad_season.parent.mkdir(parents=True)
            bad_season.write_bytes(b"x")
            bad_episode = tv / "Another Show (2024)" / "Season 01" / "Another Show - Episode 01.mkv"
            bad_episode.parent.mkdir(parents=True)
            bad_episode.write_bytes(b"x")
            ok_episode = tv / "Valid Show (2024)" / "Season 01" / "Valid Show - S01E01.mkv"
            ok_episode.parent.mkdir(parents=True)
            ok_episode.write_bytes(b"")
            ok_episode.truncate(105 * 1024 * 1024)

            results = audit_libraries(
                [
                    Library("Movies", "movie", movies),
                    Library("TV", "series", tv),
                ]
            )

        by_library = {result.name: result for result in results}
        movie_issues = {(issue.type, issue.relative_path) for issue in by_library["Movies"].issues}
        tv_issues = {(issue.type, issue.relative_path) for issue in by_library["TV"].issues}
        all_paths = [issue.relative_path for result in results for issue in result.issues]

        self.assertIn(("empty_directory", "Empty"), movie_issues)
        self.assertIn(("directory_without_video", "Images Only"), movie_issues)
        self.assertIn(("orphaned_sidecar", "Orphans/lost.srt"), movie_issues)
        self.assertIn(("invalid_movie_layout", "Loose.Movie.2024.mkv"), movie_issues)
        self.assertIn(("invalid_movie_layout", "Bad Movie/Bad Movie.mkv"), movie_issues)
        self.assertIn(("small_video_file", "Bad Movie/Bad Movie.mkv"), movie_issues)
        self.assertIn(("invalid_series_layout", "Root.Show.S01E01.mkv"), tv_issues)
        self.assertIn(("invalid_series_layout", "Pantheon (2022)/Pantheon - S01E03.mkv"), tv_issues)
        self.assertIn(("invalid_series_layout", "Good Show (2024)/Season One/Good Show - S01E01.mkv"), tv_issues)
        self.assertIn(("invalid_series_layout", "Another Show (2024)/Season 01/Another Show - Episode 01.mkv"), tv_issues)
        self.assertNotIn("沙丘 Dune (2021)/沙丘 Dune (2021).mkv", [path for issue_type, path in movie_issues if issue_type != "small_video_file"])
        self.assertFalse(any(".@__thumb" in path for path in all_paths))
        self.assertNotIn(str(root), str(by_library["Movies"].to_dict()))

    def test_audit_libraries_reports_read_error_without_stopping(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movies = root / "movies"
            movie = movies / "沙丘 Dune (2021)" / "沙丘 Dune (2021).mkv"
            movie.parent.mkdir(parents=True)
            movie.write_bytes(b"x")

            with patch("media_manager.media._file_size", side_effect=OSError("permission denied")):
                result = audit_libraries([Library("Movies", "movie", movies)])[0]

        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].type, "read_error")
        self.assertEqual(result.issues[0].relative_path, "沙丘 Dune (2021)/沙丘 Dune (2021).mkv")
        self.assertEqual(result.issues[0].detail, "permission denied")
```

同时把文件顶部 import 改为：

```python
from unittest.mock import patch
```

- [ ] **Step 2: 运行测试，确认新增测试失败**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_media
```

Expected: FAIL，错误包含 `cannot import name 'audit_libraries'`。

- [ ] **Step 3: 实现最小质量检查核心**

在 `backend/src/media_manager/media.py` 的常量区追加：

```python
SMALL_VIDEO_BYTES = 100 * 1024 * 1024
SIDECAR_EXTENSIONS = {".nfo", *SUBTITLE_EXTENSIONS}
STRICT_YEAR_RE = re.compile(r"\((?:19\d{2}|20\d{2})\)")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")
STRICT_SEASON_DIR_RE = re.compile(r"^Season (?P<season>\d{2})$")
```

在 `MediaItem` 后追加：

```python
@dataclass(frozen=True)
class AuditIssue:
    type: str
    message: str
    library: str
    relative_path: str
    size_bytes: int | None = None
    detail: str | None = None
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", f"{self.library}:{self.type}:{self.relative_path}")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AuditLibraryResult:
    name: str
    type: str
    issues: list[AuditIssue]

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "type": self.type, "issues": [issue.to_dict() for issue in self.issues]}
```

在 `scan_libraries()` 后追加：

```python
def audit_libraries(libraries: list[object]) -> list[AuditLibraryResult]:
    results: list[AuditLibraryResult] = []
    for library in libraries:
        root = Path(library.path)
        issues: list[AuditIssue] = []
        _audit_directory_state(root, library.name, issues)
        _audit_sidecars(root, library.name, issues)
        videos = _video_files(root)
        if library.kind == "movie":
            _audit_movie_layout(root, library.name, videos, issues)
        elif library.kind == "series":
            _audit_series_layout(root, library.name, videos, issues)
        _audit_small_videos(root, library.name, videos, issues)
        results.append(AuditLibraryResult(name=library.name, type=library.kind, issues=issues))
    return results


def _audit_directory_state(root: Path, library_name: str, issues: list[AuditIssue]) -> None:
    for current, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        directory = Path(current)
        if directory == root:
            continue
        file_names = [name for name in names if (directory / name).is_file()]
        if not file_names and not dirs:
            issues.append(_audit_issue(root, library_name, "empty_directory", directory, "目录为空"))
            continue
        if not any(path.suffix.lower() in VIDEO_EXTENSIONS for path in _walk_files(directory)):
            issues.append(_audit_issue(root, library_name, "directory_without_video", directory, "目录中没有视频文件"))


def _audit_sidecars(root: Path, library_name: str, issues: list[AuditIssue]) -> None:
    for file in _walk_files(root):
        if file.suffix.lower() not in SIDECAR_EXTENSIONS:
            continue
        if not _matching_video_exists(file):
            issues.append(_audit_issue(root, library_name, "orphaned_sidecar", file, "旁路文件没有对应的视频文件"))


def _audit_movie_layout(root: Path, library_name: str, videos: list[Path], issues: list[AuditIssue]) -> None:
    direct_videos_by_dir: dict[Path, list[Path]] = {}
    for video in videos:
        relative = video.relative_to(root)
        if len(relative.parts) == 1:
            issues.append(_audit_issue(root, library_name, "invalid_movie_layout", video, "电影文件直接位于媒体库根目录"))
            continue
        direct_videos_by_dir.setdefault(video.parent, []).append(video)
        name_errors = _movie_name_errors(video.parent.name, video.name)
        if name_errors:
            issues.append(_audit_issue(root, library_name, "invalid_movie_layout", video, "电影命名不规范", ", ".join(name_errors)))
    for directory, direct_videos in direct_videos_by_dir.items():
        if len(direct_videos) > 1:
            issues.append(_audit_issue(root, library_name, "invalid_movie_layout", directory, "电影目录包含多个顶层视频文件"))


def _audit_series_layout(root: Path, library_name: str, videos: list[Path], issues: list[AuditIssue]) -> None:
    for video in videos:
        relative = video.relative_to(root)
        if len(relative.parts) == 1:
            issues.append(_audit_issue(root, library_name, "invalid_series_layout", video, "视频文件直接位于剧集媒体库根目录"))
            continue
        if len(relative.parts) == 2:
            issues.append(_audit_issue(root, library_name, "invalid_series_layout", video, "剧集文件缺少季度目录"))
            continue
        if not STRICT_SEASON_DIR_RE.fullmatch(relative.parts[1]):
            issues.append(_audit_issue(root, library_name, "invalid_series_layout", video, "季度目录命名不符合 Season xx"))
        if not EPISODE_RE.search(video.stem):
            issues.append(_audit_issue(root, library_name, "invalid_series_layout", video, "单集文件名缺少 SxxExx"))


def _audit_small_videos(root: Path, library_name: str, videos: list[Path], issues: list[AuditIssue]) -> None:
    for video in videos:
        try:
            size = _file_size(video)
        except OSError as exc:
            issues.append(_audit_issue(root, library_name, "read_error", video, "读取文件失败", str(exc)))
            continue
        if size < SMALL_VIDEO_BYTES:
            issues.append(_audit_issue(root, library_name, "small_video_file", video, "视频文件小于 100 MiB", size_bytes=size))


def _audit_issue(
    root: Path,
    library_name: str,
    issue_type: str,
    path: Path,
    message: str,
    detail: str | None = None,
    size_bytes: int | None = None,
) -> AuditIssue:
    relative_path = _relative_path(root, path)
    return AuditIssue(
        type=issue_type,
        message=message,
        library=library_name,
        relative_path=relative_path,
        size_bytes=size_bytes,
        detail=detail,
    )


def _movie_name_errors(directory_name: str, file_name: str) -> list[str]:
    values = [directory_name, Path(file_name).stem]
    errors: list[str] = []
    if not all(STRICT_YEAR_RE.search(value) for value in values):
        errors.append("文件夹或文件名缺少年份圆括号")
    if not all(CJK_RE.search(value) for value in values):
        errors.append("文件夹或文件名缺少中文名")
    if not all(LATIN_RE.search(value) for value in values):
        errors.append("文件夹或文件名缺少英文名")
    return errors


def _matching_video_exists(sidecar: Path) -> bool:
    name = sidecar.name.lower()
    if name in {"movie.nfo", "tvshow.nfo"}:
        return bool(_video_files(sidecar.parent))
    return any(
        sibling.is_file()
        and sibling.suffix.lower() in VIDEO_EXTENSIONS
        and sidecar.name.startswith(sibling.stem)
        for sibling in sidecar.parent.iterdir()
    )


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _file_size(path: Path) -> int:
    return path.stat().st_size
```

- [ ] **Step 4: 运行媒体测试，确认通过**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_media
```

Expected: PASS，输出 `OK`。

- [ ] **Step 5: 提交后端检查核心**

```bash
git add backend/src/media_manager/media.py backend/tests/test_media.py
git commit -m "feat: add media library audit rules"
```

### Task 2: 审计 API

**Files:**
- Modify: `backend/tests/test_server.py`
- Modify: `backend/src/media_manager/server.py`

- [ ] **Step 1: 写审计接口失败测试**

在 `ServerTest` 内追加：

```python
    def test_audit_endpoint_returns_grouped_relative_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            empty = media_root / "movies" / "Empty"
            empty.mkdir(parents=True)
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

            response = TestClient(create_app(auth_enabled=False)).get("/api/audit")

        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["libraries"][0]["name"], "Movies")
        self.assertEqual(data["libraries"][0]["type"], "movie")
        self.assertNotIn("path", data["libraries"][0])
        self.assertEqual(data["libraries"][0]["issues"][0]["relative_path"], "Empty")
        self.assertNotIn(str(media_root), str(data))

    def test_audit_endpoint_rejects_missing_library_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "Movies"
kind = "movie"
path = "{media_root / "missing"}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            response = TestClient(create_app(auth_enabled=False)).get("/api/audit")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_library_path")
```

- [ ] **Step 2: 运行服务端测试，确认审计接口不存在**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_server
```

Expected: FAIL，`GET /api/audit` 返回 404。

- [ ] **Step 3: 增加 `GET /api/audit`**

修改 `backend/src/media_manager/server.py` 的 media import：

```python
from .media import MediaItem, audit_libraries, directory_files, scan_libraries
```

在 `media()` 路由后追加：

```python
    @app.get("/api/audit")
    def audit() -> dict[str, object]:
        libraries = _config(app).libraries
        for library in libraries:
            root = Path(library.path)
            if not root.is_dir():
                raise AppError("invalid_library_path", "媒体库目录不存在或不可访问", path=str(library.path))
        return {"libraries": [result.to_dict() for result in audit_libraries(libraries)]}
```

- [ ] **Step 4: 运行服务端测试，确认通过**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_server
```

Expected: PASS，输出 `OK`。

- [ ] **Step 5: 提交审计 API**

```bash
git add backend/src/media_manager/server.py backend/tests/test_server.py
git commit -m "feat: expose media library audit api"
```

### Task 3: 前端检查弹窗和 CSV 导出

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 增加前端审计类型**

在 `ApiError` 前追加：

```typescript
type AuditIssueType =
  | "empty_directory"
  | "directory_without_video"
  | "orphaned_sidecar"
  | "invalid_movie_layout"
  | "invalid_series_layout"
  | "small_video_file"
  | "read_error";

type AuditIssue = {
  id: string;
  type: AuditIssueType;
  message: string;
  library: string;
  relative_path: string;
  size_bytes?: number | null;
  detail?: string | null;
};

type AuditLibraryResult = {
  name: string;
  type: "movie" | "series";
  issues: AuditIssue[];
};

type AuditResponse = {
  libraries: AuditLibraryResult[];
};

type AuditFilter = AuditIssueType | "all";

type AuditDialog = AuditResponse & {
  filter: AuditFilter;
  error?: string;
};
```

- [ ] **Step 2: 增加审计状态、请求函数和 CSV 导出函数**

在 `App()` 的 state 区追加：

```typescript
  const [auditDialog, setAuditDialog] = useState<AuditDialog | null>(null);
```

在 `openFilesDialog()` 后追加：

```typescript
  async function openAuditDialog() {
    const busyKey = "audit";
    setBusy(busyKey);
    setError(null);
    try {
      const result = await request<AuditResponse>("/api/audit");
      setAuditDialog({ ...result, filter: "all", error: undefined });
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy((current) => (current === busyKey ? null : current));
    }
  }

  async function refreshAuditDialog() {
    const busyKey = "audit";
    setBusy(busyKey);
    try {
      const result = await request<AuditResponse>("/api/audit");
      setAuditDialog((current) => ({ ...result, filter: current?.filter ?? "all", error: undefined }));
    } catch (err) {
      setAuditDialog((current) => (current ? { ...current, error: messageFrom(err) } : current));
    } finally {
      setBusy((current) => (current === busyKey ? null : current));
    }
  }

  function exportAuditCsv(dialog: AuditDialog) {
    try {
      downloadText("media-library-audit.csv", auditCsv(dialog));
    } catch (err) {
      setAuditDialog((current) => (current ? { ...current, error: messageFrom(err) } : current));
    }
  }
```

- [ ] **Step 3: 把检查入口传入媒体库详情并挂载弹窗**

在 `LibraryDetailView` 调用处加入 prop：

```tsx
          onAudit={openAuditDialog}
```

在 `LibraryDetailView` 参数和类型中加入：

```typescript
  onAudit,
```

```typescript
  onAudit: () => void;
```

在 `LibraryDetailView` 的非剧集详情右侧按钮区域替换为：

```tsx
          <div className="top-actions">
            <button type="button" onClick={onAudit} disabled={busy === "audit"}>
              {busy === "audit" ? "检查中" : "检查媒体库"}
            </button>
            <button type="button" className="link-button" onClick={() => setHash({ name: "home" })}>
              返回媒体库
            </button>
          </div>
```

在 `filesDialog` 和 `batchSummary` 渲染之间加入：

```tsx
      {auditDialog ? (
        <AuditDialogView
          dialog={auditDialog}
          busy={busy}
          onChange={setAuditDialog}
          onRefresh={refreshAuditDialog}
          onExport={exportAuditCsv}
          onClose={() => setAuditDialog(null)}
        />
      ) : null}
```

- [ ] **Step 4: 增加审计弹窗组件**

在 `BatchSummaryDialog` 前追加：

```tsx
function AuditDialogView({
  dialog,
  busy,
  onChange,
  onRefresh,
  onExport,
  onClose,
}: {
  dialog: AuditDialog;
  busy: string | null;
  onChange: (dialog: AuditDialog) => void;
  onRefresh: () => void;
  onExport: (dialog: AuditDialog) => void;
  onClose: () => void;
}) {
  const allIssues = auditIssues(dialog);
  const visibleIssues = dialog.filter === "all" ? allIssues : allIssues.filter((issue) => issue.type === dialog.filter);
  const checking = busy === "audit";

  return (
    <div className="dialog-backdrop">
      <section className="dialog audit-dialog" role="dialog" aria-modal="true" aria-label="媒体库检查结果">
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭" disabled={checking}>
          X
        </button>
        <div className="section-head">
          <div>
            <h2>媒体库检查结果</h2>
            <p className="batch-progress">{checking ? "正在检查..." : `${allIssues.length} 个问题`}</p>
          </div>
          <div className="top-actions">
            <button type="button" className="link-button" onClick={onRefresh} disabled={checking}>
              重新检查
            </button>
            <button type="button" onClick={() => onExport(dialog)} disabled={checking || allIssues.length === 0}>
              导出 CSV
            </button>
          </div>
        </div>
        {dialog.error ? <p className="notice error">{dialog.error}</p> : null}
        <div className="audit-filters" aria-label="检查结果筛选">
          <button type="button" className={dialog.filter === "all" ? "audit-filter active" : "audit-filter"} onClick={() => onChange({ ...dialog, filter: "all" })}>
            全部 {allIssues.length}
          </button>
          {AUDIT_TYPES.map((type) => {
            const count = allIssues.filter((issue) => issue.type === type).length;
            return (
              <button
                key={type}
                type="button"
                className={dialog.filter === type ? "audit-filter active" : "audit-filter"}
                onClick={() => onChange({ ...dialog, filter: type })}
              >
                {AUDIT_TYPE_LABELS[type]} {count}
              </button>
            );
          })}
        </div>
        {visibleIssues.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>媒体库</th>
                  <th>问题</th>
                  <th>相对路径</th>
                  <th>详情</th>
                </tr>
              </thead>
              <tbody>
                {visibleIssues.map((issue) => (
                  <tr key={issue.id}>
                    <td>{issue.library}</td>
                    <td>{AUDIT_TYPE_LABELS[issue.type]}</td>
                    <td className="path">{issue.relative_path}</td>
                    <td>{auditDetail(issue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">{allIssues.length === 0 ? "未发现结构问题" : "当前筛选下没有问题"}</p>
        )}
        <div className="dialog-actions">
          <button type="button" className="link-button" onClick={onClose} disabled={checking}>
            取消
          </button>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 5: 增加审计辅助函数**

在 `request<T>()` 前追加：

```typescript
const AUDIT_TYPES: AuditIssueType[] = [
  "empty_directory",
  "directory_without_video",
  "orphaned_sidecar",
  "invalid_movie_layout",
  "invalid_series_layout",
  "small_video_file",
  "read_error",
];

const AUDIT_TYPE_LABELS: Record<AuditIssueType, string> = {
  empty_directory: "空目录",
  directory_without_video: "无视频目录",
  orphaned_sidecar: "孤立旁路文件",
  invalid_movie_layout: "电影结构异常",
  invalid_series_layout: "剧集结构异常",
  small_video_file: "小视频文件",
  read_error: "读取失败",
};

function auditIssues(dialog: AuditDialog) {
  return dialog.libraries.flatMap((library) => library.issues);
}

function auditDetail(issue: AuditIssue) {
  const parts = [issue.message];
  if (issue.size_bytes !== null && issue.size_bytes !== undefined) {
    parts.push(formatBytes(issue.size_bytes));
  }
  if (issue.detail) {
    parts.push(issue.detail);
  }
  return parts.join(" / ");
}

function auditCsv(dialog: AuditDialog) {
  const rows = [["媒体库", "类型", "问题", "相对路径", "详情", "大小"]];
  for (const issue of auditIssues(dialog)) {
    rows.push([
      issue.library,
      issue.type,
      AUDIT_TYPE_LABELS[issue.type],
      issue.relative_path,
      [issue.message, issue.detail].filter(Boolean).join(" / "),
      issue.size_bytes !== null && issue.size_bytes !== undefined ? formatBytes(issue.size_bytes) : "",
    ]);
  }
  return rows.map((row) => row.map(csvValue).join(",")).join("\n");
}

function csvValue(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

function downloadText(filename: string, contents: string) {
  const blob = new Blob([contents], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 6: 增加审计样式**

在 `frontend/src/style.css` 的 `.batch-rename-dialog` 后追加：

```css
.audit-dialog {
  width: min(980px, calc(100vw - 32px));
}
```

在 `.batch-counts` 后追加：

```css
.audit-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}

.audit-filter {
  min-width: 0;
  min-height: 34px;
  border-color: #c9d4d8;
  background: #fff;
  color: #1f2933;
}

.audit-filter.active {
  border-color: #1f6f64;
  background: #1f6f64;
  color: #fff;
}
```

- [ ] **Step 7: 运行前端构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS，`tsc --noEmit` 和 `vite build` 都成功。

- [ ] **Step 8: 提交前端审计交互**

```bash
git add frontend/src/App.tsx frontend/src/style.css
git commit -m "feat: add media library audit dialog"
```

### Task 4: 全量验证

**Files:**
- No source changes.

- [ ] **Step 1: 运行后端全量测试**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
```

Expected: PASS，输出 `OK`。

- [ ] **Step 2: 运行前端生产构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS，`frontend/dist` 生成成功。

- [ ] **Step 3: 检查提交状态**

Run:

```bash
git status --short
```

Expected: 只允许出现本地临时预览目录 `.superpowers/` 或构建产物忽略项；源代码和计划文件应已提交。


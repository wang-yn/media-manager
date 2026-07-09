# Emby-like 媒体库交互 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Media Manager 前端改成 Emby-like 内容优先结构：首屏只显示媒体库入口，所有设置功能移动到设置页，媒体条目操作保留在库详情页。

**Architecture:** 不扩后端 API，不引入 React Router。前端在 `App.tsx` 内用 hash 状态区分首页、媒体库详情和设置页；从现有 `libraries` 和 `media` 数据在前端聚合媒体库卡片统计，并按库过滤媒体条目。

**Tech Stack:** React 19、TypeScript、Vite、现有 FastAPI API、CSS。

---

## 文件结构

- 修改 `frontend/src/App.tsx`：拆分 hash 路由、首页、库详情、设置页、媒体库聚合函数和现有行级操作。
- 修改 `frontend/src/style.css`：新增媒体库卡片、设置页、库详情导航样式；删除或停用首屏设置面板布局。
- 修改 `docs/architecture.md`：同步首屏与设置页信息架构，保持中文。

后端文件不改。若实现时发现后端接口缺口，先用前端聚合解决。

## Task 1: 前端视图模型和 hash 路由

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 提取视图类型和 hash 解析函数**

在 `frontend/src/App.tsx` 顶部类型区增加：

```ts
type View =
  | { name: "home" }
  | { name: "settings" }
  | { name: "library"; libraryKey: string };

function parseHash(hash: string): View {
  const value = hash.replace(/^#/, "") || "/";
  if (value === "/" || value === "") {
    return { name: "home" };
  }
  if (value === "/settings") {
    return { name: "settings" };
  }
  if (value.startsWith("/libraries/")) {
    return { name: "library", libraryKey: decodeURIComponent(value.slice("/libraries/".length)) };
  }
  return { name: "home" };
}

function setHash(view: View) {
  if (view.name === "home") {
    window.location.hash = "#/";
  } else if (view.name === "settings") {
    window.location.hash = "#/settings";
  } else {
    window.location.hash = `#/libraries/${encodeURIComponent(view.libraryKey)}`;
  }
}
```

- [ ] **Step 2: 在组件中维护 view 状态**

在 `App()` 内增加：

```ts
const [view, setView] = useState<View>(() => parseHash(window.location.hash));

useEffect(() => {
  const update = () => setView(parseHash(window.location.hash));
  window.addEventListener("hashchange", update);
  update();
  return () => window.removeEventListener("hashchange", update);
}, []);
```

- [ ] **Step 3: 运行构建确认仍通过**

Run:

```bash
cd frontend && npm run build
```

Expected: `tsc --noEmit && vite build` 退出码为 0。

## Task 2: 媒体库聚合函数

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 增加媒体库摘要类型和聚合函数**

在类型区增加：

```ts
type LibrarySummary = Library & {
  key: string;
  count: number;
  missingNfo: number;
  errors: number;
};

function libraryKey(library: Pick<Library, "kind" | "path">) {
  return `${library.kind}:${library.path}`;
}

function summarizeLibraries(libraries: Library[], items: MediaItem[]): LibrarySummary[] {
  return libraries.map((library) => {
    const rows = items.filter((item) => item.library_path === library.path || item.library === library.name);
    return {
      ...library,
      key: libraryKey(library),
      count: rows.length,
      missingNfo: rows.filter((item) => !item.has_nfo).length,
      errors: 0,
    };
  });
}
```

- [ ] **Step 2: 在 `App()` 中计算 summaries 和当前库**

在 `App()` 内增加：

```ts
const summaries = summarizeLibraries(libraries, media.items);
const currentLibrary = view.name === "library" ? summaries.find((library) => library.key === view.libraryKey) : undefined;
const currentItems = currentLibrary
  ? media.items.filter((item) => item.library_path === currentLibrary.path || item.library === currentLibrary.name)
  : [];
```

- [ ] **Step 3: 运行构建确认类型正确**

Run:

```bash
cd frontend && npm run build
```

Expected: 构建通过。

## Task 3: 首页只展示媒体库入口

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 新增 `HomeView` 组件**

在 `App.tsx` 中新增：

```tsx
function HomeView({
  libraries,
  onOpenLibrary,
  onOpenSettings,
}: {
  libraries: LibrarySummary[];
  onOpenLibrary: (library: LibrarySummary) => void;
  onOpenSettings: () => void;
}) {
  if (libraries.length === 0) {
    return (
      <section className="empty-state">
        <h2>尚未配置媒体库</h2>
        <p>前往设置添加电影或剧集目录。</p>
        <button type="button" onClick={onOpenSettings}>
          前往设置
        </button>
      </section>
    );
  }
  return (
    <section className="library-grid" aria-label="媒体库">
      {libraries.map((library) => (
        <button className="library-card" type="button" key={library.key} onClick={() => onOpenLibrary(library)}>
          <span>{library.kind === "movie" ? "电影" : "剧集"}</span>
          <strong>{library.name}</strong>
          <small>{library.count} 个条目</small>
          <small>{library.missingNfo} 个缺少 NFO</small>
          <small>{library.errors} 个最近错误</small>
        </button>
      ))}
    </section>
  );
}
```

- [ ] **Step 2: 调整 `App()` 渲染，让首页不显示设置表单**

将当前 return 中媒体目录表单和影视列表直接渲染替换为按 `view.name` 分支：

```tsx
{view.name === "home" ? (
  <HomeView libraries={summaries} onOpenLibrary={(library) => setHash({ name: "library", libraryKey: library.key })} onOpenSettings={() => setHash({ name: "settings" })} />
) : null}
```

- [ ] **Step 3: 新增首页样式**

在 `style.css` 增加：

```css
.library-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.library-card {
  display: grid;
  min-height: 150px;
  padding: 18px;
  border-color: #d6dee1;
  background: #fff;
  color: #1f2933;
  text-align: left;
}

.library-card strong {
  font-size: 22px;
}

.library-card span,
.library-card small {
  color: #52616b;
}

.empty-state {
  display: grid;
  gap: 12px;
  max-width: 420px;
  padding: 28px;
  border: 1px solid #d6dee1;
  border-radius: 8px;
  background: #fff;
}
```

- [ ] **Step 4: 构建验证**

Run:

```bash
cd frontend && npm run build
```

Expected: 构建通过。

## Task 4: 设置页承载所有设置功能

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 新增 `SettingsView` 组件**

从当前 `App()` 中移动系统状态、媒体目录表单和目录列表到：

```tsx
function SettingsView({
  health,
  libraries,
  form,
  busy,
  onChangeForm,
  onAddLibrary,
}: {
  health: Health | null;
  libraries: Library[];
  form: Library;
  busy: string | null;
  onChangeForm: (form: Library) => void;
  onAddLibrary: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <>
      <section className="summary" aria-label="系统状态">
        <Status label="后端" value={health?.status ?? "unknown"} tone={health?.status === "ok" ? "good" : "warn"} />
        <Status label="配置" value={health?.config ?? "-"} />
        <Status label="媒体目录" value={health?.media_dir ?? "-"} />
        <Status label="TMDB" value="通过环境变量配置" />
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>媒体目录</h2>
        </div>
        <form className="library-form" onSubmit={onAddLibrary}>
          <input value={form.name} onChange={(event) => onChangeForm({ ...form, name: event.target.value })} placeholder="名称" required />
          <select value={form.kind} onChange={(event) => onChangeForm({ ...form, kind: event.target.value as Library["kind"] })}>
            <option value="movie">电影</option>
            <option value="series">剧集</option>
          </select>
          <input value={form.path} onChange={(event) => onChangeForm({ ...form, path: event.target.value })} placeholder="/media/movies" required />
          <button type="submit" disabled={busy === "library"}>
            添加
          </button>
        </form>
        <LibraryTable libraries={libraries} />
      </section>
    </>
  );
}
```

- [ ] **Step 2: 新增 `LibraryTable` 组件**

```tsx
function LibraryTable({ libraries }: { libraries: Library[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>名称</th>
            <th>类型</th>
            <th>路径</th>
          </tr>
        </thead>
        <tbody>
          {libraries.map((library) => (
            <tr key={`${library.kind}:${library.path}`}>
              <td>{library.name}</td>
              <td>{library.kind}</td>
              <td className="path">{library.path}</td>
            </tr>
          ))}
          {libraries.length === 0 ? (
            <tr>
              <td colSpan={3} className="empty">
                未配置媒体目录
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: 在 `App()` 中只在 `settings` 视图渲染设置页**

```tsx
{view.name === "settings" ? (
  <SettingsView health={health} libraries={libraries} form={form} busy={busy} onChangeForm={setForm} onAddLibrary={addLibrary} />
) : null}
```

- [ ] **Step 4: 构建验证**

Run:

```bash
cd frontend && npm run build
```

Expected: 构建通过。

## Task 5: 媒体库详情页保留内容操作

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 新增 `LibraryDetailView` 组件**

将当前影视列表表格和 `Row` 使用移动到：

```tsx
function LibraryDetailView({
  library,
  items,
  candidates,
  previews,
  busy,
  onBack,
  onSearch,
  onApplyMetadata,
  onPreviewRename,
  onApplyRename,
}: {
  library?: LibrarySummary;
  items: MediaItem[];
  candidates: Record<string, Candidate[]>;
  previews: Record<string, RenamePreview>;
  busy: string | null;
  onBack: () => void;
  onSearch: (item: MediaItem) => void;
  onApplyMetadata: (item: MediaItem, candidate: Candidate) => void;
  onPreviewRename: (item: MediaItem) => void;
  onApplyRename: (item: MediaItem) => void;
}) {
  if (!library) {
    return (
      <section className="empty-state">
        <h2>媒体库不存在</h2>
        <button type="button" onClick={onBack}>
          返回媒体库
        </button>
      </section>
    );
  }
  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <button className="link-button" type="button" onClick={onBack}>
            返回媒体库
          </button>
          <h2>{library.name}</h2>
        </div>
        <span>{items.length} 项</span>
      </div>
      <MediaTable
        items={items}
        candidates={candidates}
        previews={previews}
        busy={busy}
        onSearch={onSearch}
        onApplyMetadata={onApplyMetadata}
        onPreviewRename={onPreviewRename}
        onApplyRename={onApplyRename}
      />
    </section>
  );
}
```

- [ ] **Step 2: 新增 `MediaTable` 组件**

从当前影视列表 table 抽成：

```tsx
function MediaTable(props: {
  items: MediaItem[];
  candidates: Record<string, Candidate[]>;
  previews: Record<string, RenamePreview>;
  busy: string | null;
  onSearch: (item: MediaItem) => void;
  onApplyMetadata: (item: MediaItem, candidate: Candidate) => void;
  onPreviewRename: (item: MediaItem) => void;
  onApplyRename: (item: MediaItem) => void;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>标题</th>
            <th>类型</th>
            <th>季/集</th>
            <th>NFO</th>
            <th>路径</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {props.items.map((item) => (
            <Row
              key={item.id}
              item={item}
              candidates={props.candidates[item.id] ?? []}
              preview={props.previews[item.id]}
              busy={props.busy}
              onSearch={() => props.onSearch(item)}
              onApplyMetadata={(candidate) => props.onApplyMetadata(item, candidate)}
              onPreviewRename={() => props.onPreviewRename(item)}
              onApplyRename={() => props.onApplyRename(item)}
            />
          ))}
          {props.items.length === 0 ? (
            <tr>
              <td colSpan={6} className="empty">
                未发现视频
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: 在 `App()` 中渲染库详情**

```tsx
{view.name === "library" ? (
  <LibraryDetailView
    library={currentLibrary}
    items={currentItems}
    candidates={candidates}
    previews={previews}
    busy={busy}
    onBack={() => setHash({ name: "home" })}
    onSearch={searchMetadata}
    onApplyMetadata={applyMetadata}
    onPreviewRename={previewRename}
    onApplyRename={applyRename}
  />
) : null}
```

- [ ] **Step 4: 构建验证**

Run:

```bash
cd frontend && npm run build
```

Expected: 构建通过。

## Task 6: 顶部导航和错误作用域

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 修改顶部导航**

将顶部渲染调整为：

```tsx
<header className="topbar">
  <button className="brand-button" type="button" onClick={() => setHash({ name: "home" })}>
    Media Manager
  </button>
  <div className="top-actions">
    <button type="button" onClick={refresh} disabled={busy === "refresh"}>
      {busy === "refresh" ? "刷新中" : "刷新"}
    </button>
    <button type="button" onClick={() => setHash({ name: "settings" })}>
      设置
    </button>
  </div>
</header>
```

- [ ] **Step 2: 保留单个错误条，但渲染在当前视图内容上方**

继续使用当前 `error` state：

```tsx
{error ? <p className="notice error">{error}</p> : null}
```

不要在首页渲染设置错误来源的表单。

- [ ] **Step 3: 新增导航样式**

```css
.brand-button {
  min-width: 0;
  border: 0;
  background: transparent;
  color: #1f2933;
  font-size: 22px;
  font-weight: 700;
  padding: 0;
}

.top-actions {
  display: flex;
  gap: 10px;
}

.link-button {
  min-width: 0;
  min-height: 0;
  border: 0;
  background: transparent;
  color: #1f6f64;
  padding: 0 0 8px;
}
```

- [ ] **Step 4: 构建验证**

Run:

```bash
cd frontend && npm run build
```

Expected: 构建通过。

## Task 7: 全量验证和提交

**Files:**
- Modify: `docs/architecture.md`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 同步架构文档**

在 `docs/architecture.md` 前端相关位置补充：

```md
## Frontend Interaction Model

首屏采用 Emby-like 媒体库入口：`#/` 只展示媒体库卡片；`#/libraries/<id>` 展示单个媒体库内容和行级操作；`#/settings` 承载系统状态、媒体目录管理和配置提示。设置功能不得出现在首页。
```

- [ ] **Step 2: 后端测试**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
```

Expected: `OK`。

- [ ] **Step 3: 前端构建**

Run:

```bash
cd frontend && npm run build
```

Expected: `✓ built` 且退出码为 0。

- [ ] **Step 4: 空白和密钥检查**

Run:

```bash
git diff --check
rg -n 'api_key\s*=\s*"[A-Za-z0-9]{20,}"' . -g '!frontend/node_modules/**' -g '!frontend/dist/**' -g '!.venv/**'
```

Expected: `git diff --check` 退出码 0；`rg` 无命中。

- [ ] **Step 5: 手动烟测**

Run app locally and verify:

```bash
MEDIA_MANAGER_STATIC_DIR=frontend/dist MEDIA_MANAGER_CONFIG=config/config.toml MEDIA_MANAGER_HOST=127.0.0.1 MEDIA_MANAGER_PORT=8002 PYTHONPATH=backend/src .venv/bin/python -m media_manager.server
```

Expected:

- `#/` 首页只显示媒体库卡片和顶部导航。
- `#/settings` 显示系统状态和添加媒体目录表单。
- 点击媒体库卡片进入库详情，只显示该库条目。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/App.tsx frontend/src/style.css docs/architecture.md
git commit -m "feat: add emby-like library navigation"
```

## 自检

- spec 的首页、库详情、设置页均有任务覆盖。
- 所有设置功能迁移到 settings 视图。
- 首页不渲染添加目录表单、系统状态、路径或 TMDB key 提示。
- 不新增后端 API，不新增前端依赖。
- 计划文档正文为中文，保留必要英文技术名和命令。

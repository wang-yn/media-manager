import { FormEvent, useEffect, useState } from "react";

type Health = {
  status: string;
  config: string;
  media_dir: string;
  tmdb: "configured" | "missing";
};

type Library = {
  name: string;
  kind: "movie" | "series";
  path: string;
};

type MediaItem = {
  id: string;
  kind: string;
  title: string;
  path: string;
  library: string;
  library_path: string;
  year?: number;
  season?: number;
  episode?: number;
  subtitles?: string[];
  nfo_path?: string;
  has_nfo?: boolean;
};

type MediaResponse = {
  count: number;
  items: MediaItem[];
};

type Candidate = {
  id: number;
  title: string;
  year?: number;
  overview?: string;
  media_type: string;
};

type RenamePreview = {
  can_apply: boolean;
  conflicts: string[];
  changes: Array<{ from: string; to: string }>;
};

type ApiError = {
  error?: {
    code?: string;
    message?: string;
    detail?: string;
    path?: string;
  };
};

const emptyMedia: MediaResponse = { count: 0, items: [] };

type View = { name: "home" } | { name: "settings" } | { name: "library"; libraryId: string };

type LibrarySummary = Library & {
  key: string;
  count: number;
  missingNfo: number;
  errors: number;
};

export default function App() {
  const [view, setView] = useState<View>(() => parseHash());
  const [health, setHealth] = useState<Health | null>(null);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [media, setMedia] = useState<MediaResponse>(emptyMedia);
  const [form, setForm] = useState<Library>({ name: "", kind: "movie", path: "" });
  const [candidates, setCandidates] = useState<Record<string, Candidate[]>>({});
  const [previews, setPreviews] = useState<Record<string, RenamePreview>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshContent() {
    const [librariesData, mediaData] = await Promise.all([request<Library[]>("/api/libraries"), request<MediaResponse>("/api/media")]);
    setLibraries(librariesData);
    setMedia(mediaData);
  }

  async function refreshHealth() {
    setHealth(await request<Health>("/api/health"));
  }

  async function refresh() {
    setBusy("refresh");
    setError(null);
    try {
      await refreshContent();
      if (view.name === "settings") {
        await refreshHealth();
      }
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy(null);
    }
  }

  async function addLibrary(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("library");
    setError(null);
    try {
      const updated = await request<Library[]>("/api/libraries", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setLibraries(updated);
      setForm({ name: "", kind: "movie", path: "" });
      await refreshContent();
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy(null);
    }
  }

  async function searchMetadata(item: MediaItem) {
    setBusy(`search:${item.id}`);
    setError(null);
    try {
      const result = await request<{ results: Candidate[] }>(`/api/media/${item.id}/metadata/search`, { method: "POST" });
      setCandidates((current) => ({ ...current, [item.id]: result.results }));
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy(null);
    }
  }

  async function applyMetadata(item: MediaItem, candidate: Candidate) {
    setBusy(`metadata:${item.id}`);
    setError(null);
    try {
      await request<{ nfo_path: string }>(`/api/media/${item.id}/metadata/apply`, {
        method: "POST",
        body: JSON.stringify({ tmdb_id: candidate.id }),
      });
      setCandidates((current) => ({ ...current, [item.id]: [] }));
      await refreshContent();
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy(null);
    }
  }

  async function previewRename(item: MediaItem) {
    setBusy(`preview:${item.id}`);
    setError(null);
    try {
      const preview = await request<RenamePreview>(`/api/media/${item.id}/rename/preview`, { method: "POST" });
      setPreviews((current) => ({ ...current, [item.id]: preview }));
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy(null);
    }
  }

  async function applyRename(item: MediaItem) {
    if (!window.confirm(`确认执行重命名并移动文件？\n\n${item.title}`)) {
      return;
    }
    setBusy(`rename:${item.id}`);
    setError(null);
    try {
      await request(`/api/media/${item.id}/rename/apply`, { method: "POST" });
      setPreviews((current) => ({ ...current, [item.id]: { can_apply: false, conflicts: [], changes: [] } }));
      await refreshContent();
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (view.name !== "settings" || health) {
      return;
    }
    refreshHealth().catch((err) => setError(messageFrom(err)));
  }, [view.name, health]);

  useEffect(() => {
    function syncView() {
      setView(parseHash());
    }
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, []);

  const summaries = summarizeLibraries(libraries, media.items);
  const currentLibrary = view.name === "library" ? summaries.find((library) => library.key === view.libraryId) : undefined;
  const currentItems = currentLibrary ? media.items.filter((item) => itemInLibrary(item, currentLibrary)) : [];

  return (
    <main className="shell">
      <header className="topbar">
        <button type="button" className="brand-button" onClick={() => setHash({ name: "home" })}>
          <span className="eyebrow">Media Manager</span>
          <span className="brand-title">影视媒体库工作台</span>
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

      {error ? <p className="notice error">{error}</p> : null}

      {view.name === "settings" ? (
        <SettingsView health={health} libraries={libraries} media={media} form={form} busy={busy} onFormChange={setForm} onAddLibrary={addLibrary} />
      ) : null}

      {view.name === "library" ? (
        <LibraryDetailView
          library={currentLibrary}
          items={currentItems}
          candidates={candidates}
          previews={previews}
          busy={busy}
          onSearch={searchMetadata}
          onApplyMetadata={applyMetadata}
          onPreviewRename={previewRename}
          onApplyRename={applyRename}
        />
      ) : null}

      {view.name === "home" ? <HomeView summaries={summaries} /> : null}
    </main>
  );
}

function HomeView({ summaries }: { summaries: LibrarySummary[] }) {
  if (summaries.length === 0) {
    return (
      <section className="empty-state">
        <h2>还没有媒体库</h2>
        <p>先添加一个电影或剧集目录。</p>
        <button type="button" onClick={() => setHash({ name: "settings" })}>
          前往设置
        </button>
      </section>
    );
  }

  return (
    <section className="library-grid" aria-label="媒体库">
      {summaries.map((library) => (
        <button key={library.key} type="button" className="library-card" onClick={() => setHash({ name: "library", libraryId: library.key })}>
          <span>{library.kind === "series" ? "剧集" : "电影"}</span>
          <strong>{library.name}</strong>
          <small>{library.count} 个视频</small>
          <small>{library.missingNfo} 个缺少 NFO</small>
          <small>{library.errors} 个最近错误</small>
        </button>
      ))}
    </section>
  );
}

function SettingsView({
  health,
  libraries,
  media,
  form,
  busy,
  onFormChange,
  onAddLibrary,
}: {
  health: Health | null;
  libraries: Library[];
  media: MediaResponse;
  form: Library;
  busy: string | null;
  onFormChange: (form: Library) => void;
  onAddLibrary: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <>
      <section className="summary" aria-label="系统状态">
        <Status label="后端" value={health?.status ?? "unknown"} tone={health?.status === "ok" ? "good" : "warn"} />
        <Status label="配置" value={health?.config ?? "-"} />
        <Status label="媒体目录" value={health?.media_dir ?? "-"} />
        <Status label="TMDB" value={health?.tmdb === "configured" ? "已配置" : "缺失"} tone={health?.tmdb === "configured" ? "good" : "warn"} />
        <Status label="已发现" value={`${media.count} 个视频`} tone={media.count > 0 ? "good" : "warn"} />
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>媒体目录</h2>
        </div>
        <form className="library-form" onSubmit={onAddLibrary}>
          <input value={form.name} onChange={(event) => onFormChange({ ...form, name: event.target.value })} placeholder="名称" required />
          <select value={form.kind} onChange={(event) => onFormChange({ ...form, kind: event.target.value as Library["kind"] })}>
            <option value="movie">电影</option>
            <option value="series">剧集</option>
          </select>
          <input value={form.path} onChange={(event) => onFormChange({ ...form, path: event.target.value })} placeholder="/media/movies" required />
          <button type="submit" disabled={busy === "library"}>
            添加
          </button>
        </form>
        <LibraryTable libraries={libraries} />
      </section>
    </>
  );
}

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
            <tr key={libraryKey(library)}>
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

function LibraryDetailView({
  library,
  items,
  candidates,
  previews,
  busy,
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
  onSearch: (item: MediaItem) => void;
  onApplyMetadata: (item: MediaItem, candidate: Candidate) => void;
  onPreviewRename: (item: MediaItem) => void;
  onApplyRename: (item: MediaItem) => void;
}) {
  if (!library) {
    return (
      <section className="empty-state">
        <h2>未找到媒体库</h2>
        <p>该媒体库可能已被删除。</p>
        <button type="button" onClick={() => setHash({ name: "home" })}>
          返回首页
        </button>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h2>{library.name}</h2>
          <p className="path">{library.path}</p>
        </div>
        <button type="button" className="link-button" onClick={() => setHash({ name: "home" })}>
          返回媒体库
        </button>
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

function MediaTable({
  items,
  candidates,
  previews,
  busy,
  onSearch,
  onApplyMetadata,
  onPreviewRename,
  onApplyRename,
}: {
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
          {items.map((item) => (
            <Row
              key={item.id}
              item={item}
              candidates={candidates[item.id] ?? []}
              preview={previews[item.id]}
              busy={busy}
              onSearch={() => onSearch(item)}
              onApplyMetadata={(candidate) => onApplyMetadata(item, candidate)}
              onPreviewRename={() => onPreviewRename(item)}
              onApplyRename={() => onApplyRename(item)}
            />
          ))}
          {items.length === 0 ? (
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

function Row({
  item,
  candidates,
  preview,
  busy,
  onSearch,
  onApplyMetadata,
  onPreviewRename,
  onApplyRename,
}: {
  item: MediaItem;
  candidates: Candidate[];
  preview?: RenamePreview;
  busy: string | null;
  onSearch: () => void;
  onApplyMetadata: (candidate: Candidate) => void;
  onPreviewRename: () => void;
  onApplyRename: () => void;
}) {
  return (
    <>
      <tr>
        <td>{item.year ? `${item.title} (${item.year})` : item.title}</td>
        <td>{item.kind}</td>
        <td>{item.season && item.episode ? `S${pad(item.season)}E${pad(item.episode)}` : "-"}</td>
        <td className={item.has_nfo ? "good" : "warn"}>{item.has_nfo ? "已有" : "缺失"}</td>
        <td className="path">{item.path}</td>
        <td>
          <div className="actions">
            <button type="button" onClick={onSearch} disabled={busy === `search:${item.id}`}>
              刮削
            </button>
            <button type="button" onClick={onPreviewRename} disabled={busy === `preview:${item.id}`}>
              预览改名
            </button>
            <button type="button" onClick={onApplyRename} disabled={!preview?.can_apply || busy === `rename:${item.id}`}>
              执行改名
            </button>
          </div>
        </td>
      </tr>
      {candidates.length > 0 ? (
        <tr>
          <td colSpan={6}>
            <div className="inline-list">
              {candidates.map((candidate) => (
                <button key={candidate.id} type="button" className="candidate" onClick={() => onApplyMetadata(candidate)}>
                  <strong>{candidate.year ? `${candidate.title} (${candidate.year})` : candidate.title}</strong>
                  <span>{candidate.overview || "无简介"}</span>
                </button>
              ))}
            </div>
          </td>
        </tr>
      ) : null}
      {preview ? (
        <tr>
          <td colSpan={6}>
            <div className={preview.can_apply ? "preview" : "preview blocked"}>
              {preview.conflicts.length > 0 ? <p>冲突：{preview.conflicts.join(", ")}</p> : null}
              {preview.changes.map((change) => (
                <p className="path" key={`${change.from}:${change.to}`}>
                  {change.from} → {change.to}
                </p>
              ))}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function Status({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" }) {
  return (
    <div className="status">
      <span>{label}</span>
      <strong className={tone ?? ""}>{value}</strong>
    </div>
  );
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw data;
  }
  return data;
}

function messageFrom(err: unknown) {
  const api = err as ApiError;
  const error = api.error;
  if (error?.message) {
    return [error.message, error.detail, error.path].filter(Boolean).join("：");
  }
  return err instanceof Error ? err.message : "操作失败";
}

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function parseHash(): View {
  const hash = window.location.hash || "#/";
  if (hash === "#/settings") {
    return { name: "settings" };
  }
  const prefix = "#/libraries/";
  if (hash.startsWith(prefix)) {
    try {
      return { name: "library", libraryId: decodeURIComponent(hash.slice(prefix.length)) };
    } catch {
      return { name: "home" };
    }
  }
  return { name: "home" };
}

function setHash(view: View) {
  window.location.hash = view.name === "library" ? `/libraries/${encodeURIComponent(view.libraryId)}` : view.name === "settings" ? "/settings" : "/";
}

function libraryKey(library: Pick<Library, "kind" | "path">) {
  return `${library.kind}:${library.path}`;
}

function summarizeLibraries(libraries: Library[], items: MediaItem[]): LibrarySummary[] {
  return libraries.map((library) => {
    const libraryItems = items.filter((item) => itemInLibrary(item, library));
    return {
      ...library,
      key: libraryKey(library),
      count: libraryItems.length,
      missingNfo: libraryItems.filter((item) => !item.has_nfo).length,
      errors: 0,
    };
  });
}

function itemInLibrary(item: MediaItem, library: Pick<Library, "path">) {
  return item.library_path === library.path;
}

import { FormEvent, useEffect, useRef, useState } from "react";

type Health = {
  status: string;
  config: string;
  media_dir: string;
  tmdb: "configured" | "missing";
  assrt: "configured" | "missing";
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

type SubtitleCandidate = {
  id: number;
  native_name?: string;
  videoname?: string;
  lang?: string;
  subtype?: string;
  vote_score?: number;
  release_site?: string;
  upload_time?: string;
};

type SubtitleDialog = {
  item: MediaItem;
  query: string;
  results: SubtitleCandidate[];
  selectedId?: number;
  error?: string;
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
  const [subtitleDialog, setSubtitleDialog] = useState<SubtitleDialog | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const subtitleSearchId = useRef(0);

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

  function openSubtitleDialog(item: MediaItem) {
    const dialog = { item, query: videoStem(item.path), results: [] };
    setSubtitleDialog(dialog);
    searchSubtitles(dialog);
  }

  async function searchSubtitles(dialog: SubtitleDialog) {
    const searchId = subtitleSearchId.current + 1;
    subtitleSearchId.current = searchId;
    const busyKey = `subtitle-search:${dialog.item.id}`;
    setBusy(busyKey);
    try {
      const result = await request<{ query: string; results: SubtitleCandidate[] }>(`/api/media/${dialog.item.id}/subtitles/search`, {
        method: "POST",
        body: JSON.stringify({ query: dialog.query }),
      });
      setSubtitleDialog((current) =>
        current?.item.id === dialog.item.id && subtitleSearchId.current === searchId
          ? { ...current, query: result.query, results: result.results, selectedId: undefined, error: undefined }
          : current,
      );
    } catch (err) {
      setSubtitleDialog((current) => (current?.item.id === dialog.item.id && subtitleSearchId.current === searchId ? { ...current, error: messageFrom(err) } : current));
    } finally {
      if (subtitleSearchId.current === searchId) {
        setBusy((current) => (current === busyKey ? null : current));
      }
    }
  }

  async function downloadSelectedSubtitle(dialog: SubtitleDialog) {
    if (dialog.selectedId === undefined) {
      return;
    }
    const busyKey = `subtitle-download:${dialog.item.id}`;
    setBusy(busyKey);
    try {
      await request<{ path: string }>(`/api/media/${dialog.item.id}/subtitles/download`, {
        method: "POST",
        body: JSON.stringify({ subtitle_id: dialog.selectedId }),
      });
      setSubtitleDialog(null);
      await refreshContent();
    } catch (err) {
      setSubtitleDialog((current) => (current?.item.id === dialog.item.id ? { ...current, error: messageFrom(err) } : current));
    } finally {
      setBusy((current) => (current === busyKey ? null : current));
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
          onSearchSubtitle={openSubtitleDialog}
        />
      ) : null}

      {view.name === "home" ? <HomeView summaries={summaries} /> : null}

      {subtitleDialog ? (
        <SubtitleDialogView
          dialog={subtitleDialog}
          busy={busy}
          onChange={setSubtitleDialog}
          onSearch={searchSubtitles}
          onDownload={downloadSelectedSubtitle}
          onClose={() => setSubtitleDialog(null)}
        />
      ) : null}
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
        <Status label="ASSRT" value={health?.assrt === "configured" ? "已配置" : "缺失"} tone={health?.assrt === "configured" ? "good" : "warn"} />
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
  onSearchSubtitle,
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
  onSearchSubtitle: (item: MediaItem) => void;
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
        onSearchSubtitle={onSearchSubtitle}
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
  onSearchSubtitle,
}: {
  items: MediaItem[];
  candidates: Record<string, Candidate[]>;
  previews: Record<string, RenamePreview>;
  busy: string | null;
  onSearch: (item: MediaItem) => void;
  onApplyMetadata: (item: MediaItem, candidate: Candidate) => void;
  onPreviewRename: (item: MediaItem) => void;
  onApplyRename: (item: MediaItem) => void;
  onSearchSubtitle: (item: MediaItem) => void;
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
              onSearchSubtitle={() => onSearchSubtitle(item)}
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
  onSearchSubtitle,
}: {
  item: MediaItem;
  candidates: Candidate[];
  preview?: RenamePreview;
  busy: string | null;
  onSearch: () => void;
  onApplyMetadata: (candidate: Candidate) => void;
  onPreviewRename: () => void;
  onApplyRename: () => void;
  onSearchSubtitle: () => void;
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
            <button type="button" onClick={onSearchSubtitle} disabled={busy === `subtitle-search:${item.id}`}>
              字幕
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

function SubtitleDialogView({
  dialog,
  busy,
  onChange,
  onSearch,
  onDownload,
  onClose,
}: {
  dialog: SubtitleDialog;
  busy: string | null;
  onChange: (dialog: SubtitleDialog) => void;
  onSearch: (dialog: SubtitleDialog) => void;
  onDownload: (dialog: SubtitleDialog) => void;
  onClose: () => void;
}) {
  const searching = busy === `subtitle-search:${dialog.item.id}`;
  const downloading = busy === `subtitle-download:${dialog.item.id}`;

  return (
    <div className="dialog-backdrop">
      <section className="dialog" role="dialog" aria-modal="true" aria-label="搜索字幕">
        <div className="section-head">
          <div>
            <h2>搜索字幕</h2>
            <p className="path">{dialog.item.path}</p>
          </div>
          <button type="button" className="link-button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="subtitle-form">
          <input value={dialog.query} onChange={(event) => onChange({ ...dialog, query: event.target.value })} aria-label="字幕搜索关键词" />
          <button type="button" onClick={() => onSearch(dialog)} disabled={searching}>
            {searching ? "搜索中" : "重新搜索"}
          </button>
        </div>
        {dialog.error ? <p className="notice error">{dialog.error}</p> : null}
        <div className="subtitle-results">
          {dialog.results.map((candidate) => (
            <button
              key={candidate.id}
              type="button"
              className={candidate.id === dialog.selectedId ? "subtitle-candidate selected" : "subtitle-candidate"}
              onClick={() => onChange({ ...dialog, selectedId: candidate.id })}
            >
              <strong>{candidate.native_name || candidate.videoname || `字幕 ${candidate.id}`}</strong>
              {candidate.videoname ? <span>{candidate.videoname}</span> : null}
              <small>{[candidate.lang, candidate.subtype, candidate.release_site, candidate.upload_time].filter(Boolean).join(" / ") || "无详情"}</small>
            </button>
          ))}
          {dialog.results.length === 0 && !searching ? <p className="empty">暂无候选</p> : null}
        </div>
        <div className="dialog-actions">
          <button type="button" onClick={() => onDownload(dialog)} disabled={dialog.selectedId === undefined || searching || downloading}>
            {downloading ? "下载中" : "下载字幕"}
          </button>
        </div>
      </section>
    </div>
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

function videoStem(path: string) {
  const name = path.split(/[\\/]/).pop() ?? path;
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
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

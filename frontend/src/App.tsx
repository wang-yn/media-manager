import { FormEvent, useEffect, useState } from "react";

type Health = {
  status: string;
  config: string;
  media_dir: string;
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

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [media, setMedia] = useState<MediaResponse>(emptyMedia);
  const [form, setForm] = useState<Library>({ name: "", kind: "movie", path: "" });
  const [candidates, setCandidates] = useState<Record<string, Candidate[]>>({});
  const [previews, setPreviews] = useState<Record<string, RenamePreview>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setBusy("refresh");
    setError(null);
    try {
      const [healthData, librariesData, mediaData] = await Promise.all([
        request<Health>("/api/health"),
        request<Library[]>("/api/libraries"),
        request<MediaResponse>("/api/media"),
      ]);
      setHealth(healthData);
      setLibraries(librariesData);
      setMedia(mediaData);
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
      await refresh();
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
      await refresh();
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
    setBusy(`rename:${item.id}`);
    setError(null);
    try {
      await request(`/api/media/${item.id}/rename/apply`, { method: "POST" });
      setPreviews((current) => ({ ...current, [item.id]: { can_apply: false, conflicts: [], changes: [] } }));
      await refresh();
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Media Manager</p>
          <h1>影视媒体库工作台</h1>
        </div>
        <button type="button" onClick={refresh} disabled={busy === "refresh"}>
          {busy === "refresh" ? "刷新中" : "刷新"}
        </button>
      </header>

      {error ? <p className="notice error">{error}</p> : null}

      <section className="summary" aria-label="系统状态">
        <Status label="后端" value={health?.status ?? "unknown"} tone={health?.status === "ok" ? "good" : "warn"} />
        <Status label="配置" value={health?.config ?? "-"} />
        <Status label="媒体目录" value={health?.media_dir ?? "-"} />
        <Status label="已发现" value={`${media.count} 个视频`} tone={media.count > 0 ? "good" : "warn"} />
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>媒体目录</h2>
        </div>
        <form className="library-form" onSubmit={addLibrary}>
          <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="名称" required />
          <select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as Library["kind"] })}>
            <option value="movie">电影</option>
            <option value="series">剧集</option>
          </select>
          <input value={form.path} onChange={(event) => setForm({ ...form, path: event.target.value })} placeholder="/media/movies" required />
          <button type="submit" disabled={busy === "library"}>
            添加
          </button>
        </form>
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
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>影视列表</h2>
          <span>{media.count} 项</span>
        </div>
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
              {media.items.map((item) => (
                <Row
                  key={item.id}
                  item={item}
                  candidates={candidates[item.id] ?? []}
                  preview={previews[item.id]}
                  busy={busy}
                  onSearch={() => searchMetadata(item)}
                  onApplyMetadata={(candidate) => applyMetadata(item, candidate)}
                  onPreviewRename={() => previewRename(item)}
                  onApplyRename={() => applyRename(item)}
                />
              ))}
              {media.items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="empty">
                    未发现视频
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </main>
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

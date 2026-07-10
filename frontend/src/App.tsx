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

type MetadataDialog = {
  item: MediaItem;
  query: string;
  results: Candidate[];
  selectedId?: number;
  error?: string;
};

type RenameDialog = {
  item: MediaItem;
  preview?: RenamePreview;
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

type SeasonSummary = {
  key: string;
  title: string;
  year?: number;
  season: number;
  items: MediaItem[];
  representative: MediaItem;
  path: string;
  subtitles: string[];
  missingNfo: number;
};

export default function App() {
  const [view, setView] = useState<View>(() => parseHash());
  const [health, setHealth] = useState<Health | null>(null);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [media, setMedia] = useState<MediaResponse>(emptyMedia);
  const [form, setForm] = useState<Library>({ name: "", kind: "movie", path: "" });
  const [renameDialog, setRenameDialog] = useState<RenameDialog | null>(null);
  const [metadataDialog, setMetadataDialog] = useState<MetadataDialog | null>(null);
  const [subtitleDialog, setSubtitleDialog] = useState<SubtitleDialog | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const metadataSearchId = useRef(0);
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

  function openMetadataDialog(item: MediaItem) {
    const dialog = { item, query: item.title, results: [] };
    setMetadataDialog(dialog);
    searchMetadata(dialog);
  }

  async function searchMetadata(dialog: MetadataDialog) {
    const searchId = metadataSearchId.current + 1;
    metadataSearchId.current = searchId;
    const busyKey = `metadata-search:${dialog.item.id}`;
    setBusy(busyKey);
    try {
      const result = await request<{ query: string; results: Candidate[] }>(`/api/media/${dialog.item.id}/metadata/search`, {
        method: "POST",
        body: JSON.stringify({ query: dialog.query }),
      });
      setMetadataDialog((current) =>
        current?.item.id === dialog.item.id && current.query === dialog.query && metadataSearchId.current === searchId
          ? { ...current, query: result.query, results: result.results, selectedId: undefined, error: undefined }
          : current,
      );
    } catch (err) {
      setMetadataDialog((current) =>
        current?.item.id === dialog.item.id && current.query === dialog.query && metadataSearchId.current === searchId ? { ...current, error: messageFrom(err) } : current,
      );
    } finally {
      if (metadataSearchId.current === searchId) {
        setBusy((current) => (current === busyKey ? null : current));
      }
    }
  }

  async function applySelectedMetadata(dialog: MetadataDialog) {
    if (dialog.selectedId === undefined) {
      return;
    }
    const busyKey = `metadata:${dialog.item.id}`;
    setBusy(busyKey);
    try {
      await request<{ nfo_path: string }>(`/api/media/${dialog.item.id}/metadata/apply`, {
        method: "POST",
        body: JSON.stringify({ tmdb_id: dialog.selectedId }),
      });
      setMetadataDialog(null);
      await refreshContent();
    } catch (err) {
      setMetadataDialog((current) => (current?.item.id === dialog.item.id ? { ...current, error: messageFrom(err) } : current));
    } finally {
      setBusy((current) => (current === busyKey ? null : current));
    }
  }

  async function openRenameDialog(item: MediaItem) {
    const busyKey = `preview:${item.id}`;
    setRenameDialog({ item });
    setBusy(busyKey);
    setError(null);
    try {
      const preview = await request<RenamePreview>(`/api/media/${item.id}/rename/preview`, { method: "POST" });
      setRenameDialog((current) => (current?.item.id === item.id ? { ...current, preview, error: undefined } : current));
    } catch (err) {
      setRenameDialog((current) => (current?.item.id === item.id ? { ...current, error: messageFrom(err) } : current));
    } finally {
      setBusy((current) => (current === busyKey ? null : current));
    }
  }

  async function applyRename(dialog: RenameDialog) {
    if (!dialog.preview?.can_apply || !hasRenameChanges(dialog.preview)) {
      return;
    }
    const busyKey = `rename:${dialog.item.id}`;
    setBusy(busyKey);
    try {
      await request(`/api/media/${dialog.item.id}/rename/apply`, { method: "POST" });
      setRenameDialog(null);
      await refreshContent();
    } catch (err) {
      setRenameDialog((current) => (current?.item.id === dialog.item.id ? { ...current, error: messageFrom(err) } : current));
    } finally {
      setBusy((current) => (current === busyKey ? null : current));
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
          busy={busy}
          onSearch={openMetadataDialog}
          onRename={openRenameDialog}
          onSearchSubtitle={openSubtitleDialog}
        />
      ) : null}

      {view.name === "home" ? <HomeView summaries={summaries} /> : null}

      {metadataDialog ? (
        <MetadataDialogView
          dialog={metadataDialog}
          busy={busy}
          onChange={setMetadataDialog}
          onSearch={searchMetadata}
          onApply={applySelectedMetadata}
          onClose={() => setMetadataDialog(null)}
        />
      ) : null}

      {renameDialog ? (
        <RenameDialogView dialog={renameDialog} busy={busy} onApply={applyRename} onClose={() => setRenameDialog(null)} />
      ) : null}

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
  busy,
  onSearch,
  onRename,
  onSearchSubtitle,
}: {
  library?: LibrarySummary;
  items: MediaItem[];
  busy: string | null;
  onSearch: (item: MediaItem) => void;
  onRename: (item: MediaItem) => void;
  onSearchSubtitle: (item: MediaItem) => void;
}) {
  const [selectedSeasonKey, setSelectedSeasonKey] = useState<string | null>(null);

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

  const seasons = library.kind === "series" ? groupSeriesSeasons(items) : [];
  const selectedSeason = seasons.find((season) => season.key === selectedSeasonKey);

  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h2>{selectedSeason ? `${mediaTitle(selectedSeason)} / 第 ${pad(selectedSeason.season)} 季` : library.name}</h2>
          <p className="path">{selectedSeason ? relativeLibraryPath(selectedSeason.path, library.path) : library.path}</p>
        </div>
        {selectedSeason ? (
          <button type="button" className="link-button" onClick={() => setSelectedSeasonKey(null)}>
            返回季列表
          </button>
        ) : (
          <button type="button" className="link-button" onClick={() => setHash({ name: "home" })}>
            返回媒体库
          </button>
        )}
      </div>
      {library.kind === "series" && !selectedSeason ? (
        <SeasonTable seasons={seasons} busy={busy} onSearch={onSearch} onOpen={setSelectedSeasonKey} />
      ) : (
        <MediaTable
          items={selectedSeason ? selectedSeason.items : items}
          busy={busy}
          showMetadata={library.kind !== "series"}
          onSearch={onSearch}
          onRename={onRename}
          onSearchSubtitle={onSearchSubtitle}
        />
      )}
    </section>
  );
}

function SeasonTable({
  seasons,
  busy,
  onSearch,
  onOpen,
}: {
  seasons: SeasonSummary[];
  busy: string | null;
  onSearch: (item: MediaItem) => void;
  onOpen: (key: string) => void;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>剧集</th>
            <th>季</th>
            <th>集数</th>
            <th>NFO</th>
            <th>字幕</th>
            <th>路径</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {seasons.map((season) => (
            <tr key={season.key}>
              <td>{mediaTitle(season)}</td>
              <td>第 {pad(season.season)} 季</td>
              <td>{season.items.length}</td>
              <td className={season.missingNfo === 0 ? "good" : "warn"}>{seasonNfoLabel(season)}</td>
              <td>
                <SubtitleTags subtitles={season.subtitles} />
              </td>
              <td className="path">{relativeLibraryPath(season.path, season.representative.library_path)}</td>
              <td>
                <div className="actions">
                  <button type="button" onClick={() => onSearch(season.representative)} disabled={busy === `metadata-search:${season.representative.id}`}>
                    刮削
                  </button>
                  <button type="button" onClick={() => onOpen(season.key)}>
                    查看分集
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {seasons.length === 0 ? (
            <tr>
              <td colSpan={7} className="empty">
                未发现视频
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function MediaTable({
  items,
  busy,
  showMetadata = true,
  onSearch,
  onRename,
  onSearchSubtitle,
}: {
  items: MediaItem[];
  busy: string | null;
  showMetadata?: boolean;
  onSearch: (item: MediaItem) => void;
  onRename: (item: MediaItem) => void;
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
            <th>字幕</th>
            <th>路径</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <Row
              key={item.id}
              item={item}
              busy={busy}
              showMetadata={showMetadata}
              onSearch={() => onSearch(item)}
              onRename={() => onRename(item)}
              onSearchSubtitle={() => onSearchSubtitle(item)}
            />
          ))}
          {items.length === 0 ? (
            <tr>
              <td colSpan={7} className="empty">
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
  busy,
  showMetadata,
  onSearch,
  onRename,
  onSearchSubtitle,
}: {
  item: MediaItem;
  busy: string | null;
  showMetadata: boolean;
  onSearch: () => void;
  onRename: () => void;
  onSearchSubtitle: () => void;
}) {
  return (
    <tr>
      <td>{item.year ? `${item.title} (${item.year})` : item.title}</td>
      <td>{item.kind}</td>
      <td>{item.season && item.episode ? `S${pad(item.season)}E${pad(item.episode)}` : "-"}</td>
      <td className={item.has_nfo ? "good" : "warn"}>{item.has_nfo ? "已有" : "缺失"}</td>
      <td>
        <SubtitleTags subtitles={item.subtitles ?? []} />
      </td>
      <td className="path">{relativeLibraryPath(item.path, item.library_path)}</td>
      <td>
        <div className="actions">
          {showMetadata ? (
            <button type="button" onClick={onSearch} disabled={busy === `metadata-search:${item.id}`}>
              刮削
            </button>
          ) : null}
          <button type="button" onClick={onRename} disabled={busy === `preview:${item.id}` || busy === `rename:${item.id}`}>
            自动重命名
          </button>
          <button type="button" onClick={onSearchSubtitle} disabled={busy === `subtitle-search:${item.id}`}>
            字幕
          </button>
        </div>
      </td>
    </tr>
  );
}

function SubtitleTags({ subtitles }: { subtitles: string[] }) {
  if (subtitles.length === 0) {
    return (
      <div className="subtitle-tags">
        <span className="subtitle-tag muted">无字幕</span>
      </div>
    );
  }
  const languages = subtitleLanguages(subtitles);
  return (
    <div className="subtitle-tags">
      <span className="subtitle-tag good">有字幕</span>
      {languages.map((language) => (
        <span key={language} className="subtitle-tag">
          {language}
        </span>
      ))}
    </div>
  );
}

function RenameDialogView({
  dialog,
  busy,
  onApply,
  onClose,
}: {
  dialog: RenameDialog;
  busy: string | null;
  onApply: (dialog: RenameDialog) => void;
  onClose: () => void;
}) {
  const previewing = busy === `preview:${dialog.item.id}`;
  const renaming = busy === `rename:${dialog.item.id}`;
  const preview = dialog.preview;
  const changes = preview ? renameChanges(preview) : [];
  const hasChanges = changes.length > 0;
  const canApply = Boolean(preview?.can_apply && hasChanges && !previewing && !renaming);

  return (
    <div className="dialog-backdrop">
      <section className="dialog" role="dialog" aria-modal="true" aria-label="自动重命名">
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭">
          X
        </button>
        <div className="section-head">
          <div>
            <h2>自动重命名</h2>
            <p className="path">{relativeLibraryPath(dialog.item.path, dialog.item.library_path)}</p>
          </div>
        </div>
        {previewing ? <p className="empty">正在生成改名预览...</p> : null}
        {dialog.error ? <p className="notice error">{dialog.error}</p> : null}
        {preview ? (
          <div className={preview.can_apply ? "preview" : "preview blocked"}>
            {preview.conflicts.length > 0 ? <p>冲突：{preview.conflicts.join(", ")}</p> : null}
            {!hasChanges && preview.conflicts.length === 0 ? <p>已经是规范的名称，不需要再修改。</p> : null}
            {hasChanges
              ? changes.map((change) => (
                  <RenameChangePreview key={`${change.from}:${change.to}`} change={change} libraryPath={dialog.item.library_path} />
                ))
              : null}
          </div>
        ) : null}
        <div className="dialog-actions">
          {hasChanges ? (
            <button type="button" onClick={() => onApply(dialog)} disabled={!canApply}>
              {renaming ? "重命名中" : "确定"}
            </button>
          ) : null}
          <button type="button" className="link-button" onClick={onClose}>
            取消
          </button>
        </div>
      </section>
    </div>
  );
}

function RenameChangePreview({ change, libraryPath }: { change: { from: string; to: string }; libraryPath: string }) {
  const diff = filenameDiff(baseName(change.from), baseName(change.to));
  return (
    <div className="rename-change">
      <p className="rename-file-line before">
        <span className="rename-label">修改前</span>
        <code className="rename-file">{renderDiffText(diff.from)}</code>
      </p>
      <p className="rename-file-line after">
        <span className="rename-label">修改后</span>
        <code className="rename-file">{renderDiffText(diff.to)}</code>
      </p>
      <p className="rename-path path">
        {relativeLibraryPath(change.from, libraryPath)} → {relativeLibraryPath(change.to, libraryPath)}
      </p>
    </div>
  );
}

function MetadataDialogView({
  dialog,
  busy,
  onChange,
  onSearch,
  onApply,
  onClose,
}: {
  dialog: MetadataDialog;
  busy: string | null;
  onChange: (dialog: MetadataDialog) => void;
  onSearch: (dialog: MetadataDialog) => void;
  onApply: (dialog: MetadataDialog) => void;
  onClose: () => void;
}) {
  const searching = busy === `metadata-search:${dialog.item.id}`;
  const applying = busy === `metadata:${dialog.item.id}`;

  return (
    <div className="dialog-backdrop">
      <section className="dialog" role="dialog" aria-modal="true" aria-label="刮削元数据">
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭">
          X
        </button>
        <div className="section-head">
          <div>
            <h2>刮削元数据</h2>
            <p className="path">{relativeLibraryPath(dialog.item.path, dialog.item.library_path)}</p>
          </div>
        </div>
        <div className="subtitle-form">
          <input value={dialog.query} onChange={(event) => onChange({ ...dialog, query: event.target.value })} aria-label="元数据匹配关键字" />
          <button type="button" onClick={() => onSearch(dialog)} disabled={searching}>
            {searching ? "匹配中" : "重新匹配"}
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
              <strong>{candidate.year ? `${candidate.title} (${candidate.year})` : candidate.title}</strong>
              <small>{candidate.media_type}</small>
              <span>{candidate.overview || "无简介"}</span>
            </button>
          ))}
          {dialog.results.length === 0 && !searching ? <p className="empty">暂无候选</p> : null}
        </div>
        <div className="dialog-actions">
          <button type="button" onClick={() => onApply(dialog)} disabled={dialog.selectedId === undefined || searching || applying}>
            {applying ? "写入中" : "确定"}
          </button>
          <button type="button" className="link-button" onClick={onClose}>
            取消
          </button>
        </div>
      </section>
    </div>
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
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭">
          X
        </button>
        <div className="section-head">
          <div>
            <h2>搜索字幕</h2>
            <p className="path">{relativeLibraryPath(dialog.item.path, dialog.item.library_path)}</p>
          </div>
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
          <button type="button" className="link-button" onClick={onClose}>
            取消
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
  const name = baseName(path);
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

function baseName(path: string) {
  return path.split(/[\\/]/).pop() ?? path;
}

function filenameDiff(from: string, to: string) {
  let prefixLength = 0;
  while (prefixLength < from.length && prefixLength < to.length && from[prefixLength] === to[prefixLength]) {
    prefixLength += 1;
  }
  let fromSuffix = from.length;
  let toSuffix = to.length;
  while (fromSuffix > prefixLength && toSuffix > prefixLength && from[fromSuffix - 1] === to[toSuffix - 1]) {
    fromSuffix -= 1;
    toSuffix -= 1;
  }
  return {
    from: { prefix: from.slice(0, prefixLength), diff: from.slice(prefixLength, fromSuffix), suffix: from.slice(fromSuffix) },
    to: { prefix: to.slice(0, prefixLength), diff: to.slice(prefixLength, toSuffix), suffix: to.slice(toSuffix) },
  };
}

function renderDiffText(part: { prefix: string; diff: string; suffix: string }) {
  return (
    <>
      {part.prefix}
      {part.diff ? <mark className="rename-diff">{part.diff}</mark> : null}
      {part.suffix}
    </>
  );
}

function groupSeriesSeasons(items: MediaItem[]) {
  const seasons = new Map<string, SeasonSummary>();
  for (const item of items) {
    const seasonNumber = item.season ?? 1;
    const key = [item.title, item.year ?? "", seasonNumber].join("\u0000");
    const current = seasons.get(key);
    if (current) {
      current.items.push(item);
      current.subtitles.push(...(item.subtitles ?? []));
      current.missingNfo += item.has_nfo ? 0 : 1;
      continue;
    }
    seasons.set(key, {
      key,
      title: item.title,
      year: item.year,
      season: seasonNumber,
      items: [item],
      representative: item,
      path: dirname(item.path),
      subtitles: [...(item.subtitles ?? [])],
      missingNfo: item.has_nfo ? 0 : 1,
    });
  }
  return [...seasons.values()].sort((left, right) => mediaTitle(left).localeCompare(mediaTitle(right), "zh-CN") || left.season - right.season);
}

function mediaTitle(item: Pick<MediaItem, "title" | "year">) {
  return item.year ? `${item.title} (${item.year})` : item.title;
}

function seasonNfoLabel(season: SeasonSummary) {
  if (season.missingNfo === 0) {
    return "已有";
  }
  if (season.missingNfo === season.items.length) {
    return "缺失";
  }
  return `${season.items.length - season.missingNfo}/${season.items.length}`;
}

function dirname(path: string) {
  const normalized = path.replaceAll("\\", "/");
  const index = normalized.lastIndexOf("/");
  return index > 0 ? normalized.slice(0, index) : path;
}

function subtitleLanguages(subtitles: string[]) {
  const languageByToken: Record<string, string> = {
    zh: "中文",
    cn: "中文",
    chs: "简中",
    sc: "简中",
    cht: "繁中",
    tc: "繁中",
    en: "英文",
    eng: "英文",
    ja: "日文",
    jpn: "日文",
    jp: "日文",
    ko: "韩文",
    kr: "韩文",
    kor: "韩文",
  };
  const languages = new Set<string>();
  for (const subtitle of subtitles) {
    const tokens = videoStem(subtitle).toLowerCase().split(/[ ._\-[\]()]+/).filter(Boolean);
    for (const token of tokens) {
      const language = languageByToken[token];
      if (language) {
        languages.add(language);
      }
    }
  }
  return languages.size > 0 ? [...languages].sort() : ["未知语言"];
}

function relativeLibraryPath(path: string, libraryPath: string) {
  const normalizedPath = path.replaceAll("\\", "/");
  const normalizedRoot = libraryPath.replaceAll("\\", "/").replace(/\/+$/, "");
  if (normalizedPath === normalizedRoot) {
    return ".";
  }
  const prefix = `${normalizedRoot}/`;
  return normalizedPath.startsWith(prefix) ? normalizedPath.slice(prefix.length) : path;
}

function renameChanges(preview: RenamePreview) {
  return preview.changes.filter((change) => change.from !== change.to);
}

function hasRenameChanges(preview: RenamePreview) {
  return renameChanges(preview).length > 0;
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

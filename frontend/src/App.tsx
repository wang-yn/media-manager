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
  has_metadata: boolean;
  rename_needed: boolean;
  directory_size_bytes?: number;
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

type BatchRenameEntry = {
  target: BatchTarget;
  preview?: RenamePreview;
  error?: string;
};

type BatchRenameDialog = {
  entries: BatchRenameEntry[];
};

type FilesDialog = {
  item: MediaItem;
  rootPath?: string;
  totalSizeBytes?: number;
  files?: MediaFile[];
  error?: string;
};

type MediaFile = {
  path: string;
  size_bytes: number;
};

type RenamePreview = {
  can_apply: boolean;
  conflicts: string[];
  changes: Array<{ from: string; to: string }>;
};

type IssueFilter = "missing-metadata" | "missing-subtitles" | "rename-needed";

type BatchTarget = {
  key: string;
  item: MediaItem;
  items: MediaItem[];
};

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

type SeriesSummary = {
  key: string;
  title: string;
  year?: number;
  seasons: number[];
  items: MediaItem[];
  representative: MediaItem;
  path: string;
  subtitles: string[];
  missingNfo: number;
  hasMetadata: boolean;
  renameNeeded: boolean;
  missingSubtitles: number;
  directorySizeBytes: number;
};

export default function App() {
  const [view, setView] = useState<View>(() => parseHash());
  const [health, setHealth] = useState<Health | null>(null);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [media, setMedia] = useState<MediaResponse>(emptyMedia);
  const [form, setForm] = useState<Library>({ name: "", kind: "movie", path: "" });
  const [renameDialog, setRenameDialog] = useState<RenameDialog | null>(null);
  const [batchRenameDialog, setBatchRenameDialog] = useState<BatchRenameDialog | null>(null);
  const [metadataDialog, setMetadataDialog] = useState<MetadataDialog | null>(null);
  const [subtitleDialog, setSubtitleDialog] = useState<SubtitleDialog | null>(null);
  const [guidedBatch, setGuidedBatch] = useState<GuidedBatch | null>(null);
  const [batchSummary, setBatchSummary] = useState<BatchSummary | null>(null);
  const [filesDialog, setFilesDialog] = useState<FilesDialog | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [batchRenameApplying, setBatchRenameApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const metadataSearchId = useRef(0);
  const subtitleSearchId = useRef(0);
  const guidedBatchRef = useRef<GuidedBatch | null>(null);
  const guidedBatchRunId = useRef(0);
  const batchRenameApplyingRef = useRef(false);

  function setGuidedBatchState(next: GuidedBatch | null) {
    guidedBatchRef.current = next;
    setGuidedBatch(next);
  }

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
    const batchRunId = guidedBatchRef.current?.kind === "metadata" ? guidedBatchRunId.current : undefined;
    const busyKey = `metadata:${dialog.item.id}`;
    setBusy(busyKey);
    try {
      await request<{ nfo_path: string }>(`/api/media/${dialog.item.id}/metadata/apply`, {
        method: "POST",
        body: JSON.stringify({ tmdb_id: dialog.selectedId }),
      });
      if (batchRunId !== undefined) {
        if (guidedBatchRunId.current === batchRunId && guidedBatchRef.current?.items[guidedBatchRef.current.index]?.id === dialog.item.id) {
          advanceGuidedBatch("success");
        }
        return;
      }
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

  async function openBatchRenameDialog(targets: BatchTarget[]) {
    if (targets.length === 0) {
      return;
    }
    const busyKey = "batch-rename-preview";
    setBusy(busyKey);
    setError(null);
    const entries = await Promise.all(
      targets.map(async (target) => {
        const url = isSeriesBatchTarget(target) ? `/api/media/${target.item.id}/rename/batch/preview` : `/api/media/${target.item.id}/rename/preview`;
        try {
          const preview = await request<RenamePreview>(url, { method: "POST" });
          return { target, preview };
        } catch (err) {
          return { target, error: messageFrom(err) };
        }
      }),
    );
    setBatchRenameDialog({ entries: markDuplicateRenameTargets(entries) });
    setBusy((current) => (current === busyKey ? null : current));
  }

  async function applyBatchRename(dialog: BatchRenameDialog) {
    if (batchRenameApplyingRef.current) {
      return;
    }
    const busyKey = "batch-rename-apply";
    const results: BatchResult[] = [];
    batchRenameApplyingRef.current = true;
    setBatchRenameApplying(true);
    setBusy(busyKey);
    setError(null);
    try {
      for (const entry of dialog.entries) {
        const label = mediaTitle(entry.target.item);
        const changes = entry.preview ? renameChanges(entry.preview) : [];
        if (entry.error) {
          results.push({ label, status: "failed", error: entry.error });
          continue;
        }
        if (!entry.preview?.can_apply) {
          results.push({ label, status: "failed", error: entry.preview?.conflicts.join(", ") || "重命名存在冲突" });
          continue;
        }
        if (changes.length === 0) {
          results.push({ label, status: "skipped" });
          continue;
        }
        const url = isSeriesBatchTarget(entry.target) ? `/api/media/${entry.target.item.id}/rename/batch` : `/api/media/${entry.target.item.id}/rename/apply`;
        try {
          await request(url, { method: "POST" });
          results.push({ label, status: "success" });
        } catch (err) {
          results.push({ label, status: "failed", error: messageFrom(err) });
        }
      }
      setBatchRenameDialog(null);
      setBatchSummary({ title: "批量重命名结果", results });
      await refreshContent();
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      batchRenameApplyingRef.current = false;
      setBatchRenameApplying(false);
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
    const batchRunId = guidedBatchRef.current?.kind === "subtitle" ? guidedBatchRunId.current : undefined;
    const busyKey = `subtitle-download:${dialog.item.id}`;
    setBusy(busyKey);
    try {
      await request<{ path: string }>(`/api/media/${dialog.item.id}/subtitles/download`, {
        method: "POST",
        body: JSON.stringify({ subtitle_id: dialog.selectedId }),
      });
      if (batchRunId !== undefined) {
        if (guidedBatchRunId.current === batchRunId && guidedBatchRef.current?.items[guidedBatchRef.current.index]?.id === dialog.item.id) {
          advanceGuidedBatch("success");
        }
        return;
      }
      setSubtitleDialog(null);
      await refreshContent();
    } catch (err) {
      setSubtitleDialog((current) => (current?.item.id === dialog.item.id ? { ...current, error: messageFrom(err) } : current));
    } finally {
      setBusy((current) => (current === busyKey ? null : current));
    }
  }

  async function deleteSeries(item: MediaItem) {
    const path = seriesDirectoryPath(item);
    if (!window.confirm(`确定删除剧集目录 ${relativeLibraryPath(path, item.library_path)}？此操作会删除目录下所有文件。`)) {
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

  async function openFilesDialog(item: MediaItem) {
    const busyKey = `files:${item.id}`;
    setFilesDialog({ item });
    setBusy(busyKey);
    setError(null);
    try {
      const result = await request<{ root_path: string; total_size_bytes: number; files: MediaFile[] }>(`/api/media/${item.id}/files`);
      setFilesDialog((current) =>
        current?.item.id === item.id ? { ...current, rootPath: result.root_path, totalSizeBytes: result.total_size_bytes, files: result.files, error: undefined } : current,
      );
    } catch (err) {
      setFilesDialog((current) => (current?.item.id === item.id ? { ...current, error: messageFrom(err) } : current));
    } finally {
      setBusy((current) => (current === busyKey ? null : current));
    }
  }

  function openGuidedBatchItem(kind: GuidedBatchKind, item: MediaItem) {
    if (kind === "metadata") {
      openMetadataDialog(item);
      return;
    }
    openSubtitleDialog(item);
  }

  function startGuidedBatch(kind: GuidedBatchKind, items: MediaItem[], skipped: MediaItem[]) {
    const results = skipped.map((item) => ({ label: guidedBatchLabel(kind, item), status: "skipped" as const }));
    setBatchSummary(null);
    guidedBatchRunId.current += 1;
    if (items.length === 0) {
      setGuidedBatchState(null);
      setBatchSummary({ title: guidedBatchSummaryTitle(kind), results });
      return;
    }
    const next = { kind, items, index: 0, results };
    setGuidedBatchState(next);
    openGuidedBatchItem(kind, items[0]);
  }

  function startMetadataBatch(targets: BatchTarget[]) {
    const items: MediaItem[] = [];
    const skipped: MediaItem[] = [];
    for (const target of targets) {
      if (target.item.has_metadata) {
        skipped.push(target.item);
      } else {
        items.push(target.item);
      }
    }
    startGuidedBatch("metadata", items, skipped);
  }

  function startSubtitleBatch(targets: BatchTarget[]) {
    const items = targets.flatMap((target) => target.items).sort(compareEpisodes);
    startGuidedBatch(
      "subtitle",
      items.filter((item) => (item.subtitles ?? []).length === 0),
      items.filter((item) => (item.subtitles ?? []).length > 0),
    );
  }

  function finishGuidedBatch(results: BatchResult[], kind?: GuidedBatchKind) {
    const title = guidedBatchSummaryTitle(kind ?? guidedBatchRef.current?.kind ?? "metadata");
    guidedBatchRunId.current += 1;
    setGuidedBatchState(null);
    setMetadataDialog(null);
    setSubtitleDialog(null);
    setBatchSummary({ title, results });
    refreshContent().catch((err) => setError(messageFrom(err)));
  }

  function advanceGuidedBatch(status: "success" | "skipped") {
    const batch = guidedBatchRef.current;
    if (!batch) {
      return;
    }
    const current = batch.items[batch.index];
    const results = [...batch.results, { label: guidedBatchLabel(batch.kind, current), status }];
    const nextIndex = batch.index + 1;
    if (nextIndex >= batch.items.length) {
      finishGuidedBatch(results, batch.kind);
      return;
    }
    const next = { ...batch, index: nextIndex, results };
    setGuidedBatchState(next);
    openGuidedBatchItem(batch.kind, batch.items[nextIndex]);
  }

  function skipGuidedBatch() {
    advanceGuidedBatch("skipped");
  }

  function cancelGuidedBatch() {
    const batch = guidedBatchRef.current;
    if (!batch) {
      setMetadataDialog(null);
      setSubtitleDialog(null);
      return;
    }
    const current = batch.items[batch.index];
    const error = batch.kind === "metadata" ? metadataDialog?.error : subtitleDialog?.error;
    const currentResult: BatchResult = error
      ? { label: guidedBatchLabel(batch.kind, current), status: "failed", error }
      : { label: guidedBatchLabel(batch.kind, current), status: "skipped" };
    const remaining = batch.items.slice(batch.index + 1).map((item) => ({ label: guidedBatchLabel(batch.kind, item), status: "skipped" as const }));
    finishGuidedBatch([...batch.results, currentResult, ...remaining], batch.kind);
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
          <button type="button" onClick={refresh} disabled={busy === "refresh" || batchRenameApplying}>
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
          onDeleteSeries={deleteSeries}
          onShowFiles={openFilesDialog}
          onBatchRename={openBatchRenameDialog}
          onBatchMetadata={startMetadataBatch}
          onBatchSubtitles={startSubtitleBatch}
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
          onClose={cancelGuidedBatch}
          progress={guidedBatch?.kind === "metadata" ? { current: guidedBatch.index + 1, total: guidedBatch.items.length } : undefined}
          onSkip={guidedBatch?.kind === "metadata" ? skipGuidedBatch : undefined}
        />
      ) : null}

      {renameDialog ? (
        <RenameDialogView dialog={renameDialog} busy={busy} onApply={applyRename} onClose={() => setRenameDialog(null)} />
      ) : null}

      {batchRenameDialog ? (
        <BatchRenameDialogView dialog={batchRenameDialog} applying={batchRenameApplying} onApply={applyBatchRename} onClose={() => setBatchRenameDialog(null)} />
      ) : null}

      {subtitleDialog ? (
        <SubtitleDialogView
          dialog={subtitleDialog}
          busy={busy}
          onChange={setSubtitleDialog}
          onSearch={searchSubtitles}
          onDownload={downloadSelectedSubtitle}
          onClose={cancelGuidedBatch}
          progress={guidedBatch?.kind === "subtitle" ? { current: guidedBatch.index + 1, total: guidedBatch.items.length } : undefined}
          onSkip={guidedBatch?.kind === "subtitle" ? skipGuidedBatch : undefined}
        />
      ) : null}

      {filesDialog ? <FilesDialogView dialog={filesDialog} busy={busy} onClose={() => setFilesDialog(null)} /> : null}
      {batchSummary ? <BatchSummaryDialog summary={batchSummary} onClose={() => setBatchSummary(null)} /> : null}
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
  onDeleteSeries,
  onShowFiles,
  onBatchRename,
  onBatchMetadata,
  onBatchSubtitles,
}: {
  library?: LibrarySummary;
  items: MediaItem[];
  busy: string | null;
  onSearch: (item: MediaItem) => void;
  onRename: (item: MediaItem) => void;
  onSearchSubtitle: (item: MediaItem) => void;
  onDeleteSeries: (item: MediaItem) => void;
  onShowFiles: (item: MediaItem) => void;
  onBatchRename: (targets: BatchTarget[]) => void;
  onBatchMetadata: (targets: BatchTarget[]) => void;
  onBatchSubtitles: (targets: BatchTarget[]) => void;
}) {
  const [selectedSeriesKey, setSelectedSeriesKey] = useState<string | null>(null);
  const [issueFilters, setIssueFilters] = useState<IssueFilter[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);

  useEffect(() => {
    setSelectedSeriesKey(null);
    setIssueFilters([]);
    setSelectedKeys([]);
  }, [library?.key]);

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

  const series = library.kind === "series" ? groupSeriesShows(items) : [];
  const selectedSeries = series.find((show) => show.key === selectedSeriesKey);
  const visibleSeries = series.filter((show) => seriesMatchesIssues(show, issueFilters));
  const visibleItems = items.filter((item) => mediaMatchesIssues(item, issueFilters));
  const visibleTargets: BatchTarget[] =
    library.kind === "series"
      ? visibleSeries.map((show) => ({ key: show.key, item: show.representative, items: show.items }))
      : visibleItems.map((item) => ({ key: item.id, item, items: [item] }));
  const selectedTargets = visibleTargets.filter((target) => selectedKeys.includes(target.key));
  const canBatchMetadata = selectedTargets.some((target) => !target.item.has_metadata);
  const canBatchSubtitles = selectedTargets.some((target) => target.items.some((item) => (item.subtitles ?? []).length === 0));
  const canBatchRename = selectedTargets.some((target) => target.items.some((item) => item.rename_needed));

  function toggleIssueFilter(filter: IssueFilter) {
    setIssueFilters((current) => (current.includes(filter) ? current.filter((item) => item !== filter) : [...current, filter]));
    setSelectedKeys([]);
  }

  function toggleSelectedKey(key: string) {
    setSelectedKeys((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  }

  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h2>{selectedSeries ? mediaTitle(selectedSeries) : library.name}</h2>
          <p className="path">{selectedSeries ? relativeLibraryPath(selectedSeries.path, library.path) : library.path}</p>
        </div>
        {selectedSeries ? (
          <div className="top-actions">
            <button
              type="button"
              onClick={() => onBatchRename([{ key: selectedSeries.key, item: selectedSeries.representative, items: selectedSeries.items }])}
              disabled={busy === "batch-rename-preview"}
            >
              {busy === "batch-rename-preview" ? "生成预览中" : "批量重命名"}
            </button>
            <button type="button" className="link-button" onClick={() => setSelectedSeriesKey(null)}>
              返回剧集列表
            </button>
          </div>
        ) : (
          <button type="button" className="link-button" onClick={() => setHash({ name: "home" })}>
            返回媒体库
          </button>
        )}
      </div>
      {!selectedSeries ? (
        <>
          <IssueFilterBar filters={issueFilters} onToggle={toggleIssueFilter} />
          <div className="batch-toolbar">
            <span>已选择 {selectedTargets.length} 项</span>
            <button type="button" className="link-button" onClick={() => setSelectedKeys(visibleTargets.map((target) => target.key))} disabled={visibleTargets.length === 0}>
              全选当前结果
            </button>
            <button type="button" className="link-button" onClick={() => setSelectedKeys([])} disabled={selectedKeys.length === 0}>
              清空选择
            </button>
            <button type="button" onClick={() => onBatchMetadata(selectedTargets)} disabled={!canBatchMetadata}>
              批量刮削
            </button>
            <button type="button" onClick={() => onBatchSubtitles(selectedTargets)} disabled={!canBatchSubtitles}>
              批量字幕
            </button>
            <button type="button" onClick={() => onBatchRename(selectedTargets)} disabled={!canBatchRename || busy === "batch-rename-preview"}>
              {busy === "batch-rename-preview" ? "生成预览中" : "批量重命名"}
            </button>
          </div>
        </>
      ) : null}
      {library.kind === "series" && !selectedSeries ? (
        <SeriesTable
          series={visibleSeries}
          selectedKeys={selectedKeys}
          onToggle={toggleSelectedKey}
          busy={busy}
          onSearch={onSearch}
          onOpen={setSelectedSeriesKey}
          onDelete={onDeleteSeries}
          onShowFiles={onShowFiles}
        />
      ) : (
        <MediaTable
          items={selectedSeries ? selectedSeries.items : visibleItems}
          selectedKeys={selectedSeries ? undefined : selectedKeys}
          onToggle={selectedSeries ? undefined : toggleSelectedKey}
          busy={busy}
          showMetadata={library.kind !== "series"}
          onSearch={onSearch}
          onRename={onRename}
          onSearchSubtitle={onSearchSubtitle}
          onShowFiles={onShowFiles}
        />
      )}
    </section>
  );
}

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

function SeriesTable({
  series,
  selectedKeys,
  onToggle,
  busy,
  onSearch,
  onOpen,
  onDelete,
  onShowFiles,
}: {
  series: SeriesSummary[];
  selectedKeys: string[];
  onToggle: (key: string) => void;
  busy: string | null;
  onSearch: (item: MediaItem) => void;
  onOpen: (key: string) => void;
  onDelete: (item: MediaItem) => void;
  onShowFiles: (item: MediaItem) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="media-table">
        <thead>
          <tr>
            <th className="selection-cell" aria-label="选择"></th>
            <th>剧集</th>
            <th>季数</th>
            <th>集数</th>
            <th>NFO</th>
            <th>字幕</th>
            <th>大小</th>
            <th>路径</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {series.map((show) => (
            <tr key={show.key}>
              <td className="selection-cell">
                <input type="checkbox" checked={selectedKeys.includes(show.key)} onChange={() => onToggle(show.key)} aria-label={`选择 ${mediaTitle(show)}`} />
              </td>
              <td>{mediaTitle(show)}</td>
              <td>{seasonCountLabel(show)}</td>
              <td>{show.items.length}</td>
              <td className={show.missingNfo === 0 ? "good" : "warn"}>{nfoLabel(show)}</td>
              <td>
                <SubtitleTags subtitles={show.subtitles} />
              </td>
              <td>
                <DirectorySizeTag size={show.directorySizeBytes} />
              </td>
              <td className="path">{relativeLibraryPath(show.path, show.representative.library_path)}</td>
              <td>
                <div className="actions">
                  <button type="button" onClick={() => onSearch(show.representative)} disabled={busy === `metadata-search:${show.representative.id}`}>
                    刮削
                  </button>
                  <button type="button" onClick={() => onOpen(show.key)}>
                    查看详情
                  </button>
                  <button type="button" onClick={() => onShowFiles(show.representative)} disabled={busy === `files:${show.representative.id}`}>
                    详细文件
                  </button>
                  <button type="button" className="danger-button" onClick={() => onDelete(show.representative)} disabled={busy === `delete:${show.representative.id}`}>
                    {busy === `delete:${show.representative.id}` ? "删除中" : "删除"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {series.length === 0 ? (
            <tr>
              <td colSpan={9} className="empty">
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
  selectedKeys,
  onToggle,
  busy,
  showMetadata = true,
  onSearch,
  onRename,
  onSearchSubtitle,
  onShowFiles,
}: {
  items: MediaItem[];
  selectedKeys?: string[];
  onToggle?: (key: string) => void;
  busy: string | null;
  showMetadata?: boolean;
  onSearch: (item: MediaItem) => void;
  onRename: (item: MediaItem) => void;
  onSearchSubtitle: (item: MediaItem) => void;
  onShowFiles: (item: MediaItem) => void;
}) {
  const selectable = Boolean(selectedKeys && onToggle);
  return (
    <div className="table-wrap">
      <table className="media-table">
        <thead>
          <tr>
            {selectable ? <th className="selection-cell" aria-label="选择"></th> : null}
            <th>标题</th>
            <th>类型</th>
            <th>季/集</th>
            <th>NFO</th>
            <th>字幕</th>
            <th>大小</th>
            <th>路径</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <Row
              key={item.id}
              item={item}
              selected={selectable ? selectedKeys?.includes(item.id) : undefined}
              busy={busy}
              showMetadata={showMetadata}
              onToggle={selectable ? () => onToggle?.(item.id) : undefined}
              onSearch={() => onSearch(item)}
              onRename={() => onRename(item)}
              onSearchSubtitle={() => onSearchSubtitle(item)}
              onShowFiles={() => onShowFiles(item)}
            />
          ))}
          {items.length === 0 ? (
            <tr>
              <td colSpan={selectable ? 9 : 8} className="empty">
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
  selected,
  busy,
  showMetadata,
  onToggle,
  onSearch,
  onRename,
  onSearchSubtitle,
  onShowFiles,
}: {
  item: MediaItem;
  selected?: boolean;
  busy: string | null;
  showMetadata: boolean;
  onToggle?: () => void;
  onSearch: () => void;
  onRename: () => void;
  onSearchSubtitle: () => void;
  onShowFiles: () => void;
}) {
  return (
    <tr>
      {onToggle ? (
        <td className="selection-cell">
          <input type="checkbox" checked={Boolean(selected)} onChange={onToggle} aria-label={`选择 ${mediaTitle(item)}`} />
        </td>
      ) : null}
      <td>{item.year ? `${item.title} (${item.year})` : item.title}</td>
      <td>{item.kind}</td>
      <td>{item.season && item.episode ? `S${pad(item.season)}E${pad(item.episode)}` : "-"}</td>
      <td className={item.has_nfo ? "good" : "warn"}>{item.has_nfo ? "已有" : "缺失"}</td>
      <td>
        <SubtitleTags subtitles={item.subtitles ?? []} />
      </td>
      <td>
        <DirectorySizeTag size={item.directory_size_bytes ?? 0} />
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
          <button type="button" onClick={onShowFiles} disabled={busy === `files:${item.id}`}>
            详细文件
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

function DirectorySizeTag({ size }: { size: number }) {
  return (
    <div className="subtitle-tags">
      <span className="subtitle-tag">{formatBytes(size)}</span>
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

function BatchRenameDialogView({
  dialog,
  applying,
  onApply,
  onClose,
}: {
  dialog: BatchRenameDialog;
  applying: boolean;
  onApply: (dialog: BatchRenameDialog) => void;
  onClose: () => void;
}) {
  const executable = dialog.entries.some((entry) => Boolean(entry.preview?.can_apply && hasRenameChanges(entry.preview)));

  return (
    <div className="dialog-backdrop">
      <section className="dialog batch-rename-dialog" role="dialog" aria-modal="true" aria-label="批量重命名预览">
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭" disabled={applying}>
          X
        </button>
        <div className="section-head">
          <h2>批量重命名预览</h2>
        </div>
        <div className="batch-rename-groups">
          {dialog.entries.map((entry) => {
            const preview = entry.preview;
            const changes = preview ? renameChanges(preview) : [];
            return (
              <section className="batch-rename-group" key={entry.target.key}>
                <h3>{mediaTitle(entry.target.item)}</h3>
                {entry.error ? <p className="notice error">{entry.error}</p> : null}
                {preview ? (
                  <div className={preview.can_apply ? "preview" : "preview blocked"}>
                    {preview.conflicts.length > 0 ? <p>冲突：{preview.conflicts.join(", ")}</p> : null}
                    {changes.length === 0 && preview.conflicts.length === 0 ? <p>已经是规范名称，无需修改。</p> : null}
                    {changes.map((change) => (
                      <RenameChangePreview key={`${change.from}:${change.to}`} change={change} libraryPath={entry.target.item.library_path} />
                    ))}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
        <div className="dialog-actions">
          <button type="button" onClick={() => onApply(dialog)} disabled={!executable || applying}>
            {applying ? "重命名中" : "确定"}
          </button>
          <button type="button" className="link-button" onClick={onClose} disabled={applying}>
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

function FilesDialogView({ dialog, busy, onClose }: { dialog: FilesDialog; busy: string | null; onClose: () => void }) {
  const loading = busy === `files:${dialog.item.id}`;
  const files = dialog.files ?? [];
  return (
    <div className="dialog-backdrop">
      <section className="dialog" role="dialog" aria-modal="true" aria-label="详细文件">
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭">
          X
        </button>
        <div className="section-head">
          <div>
            <h2>详细文件</h2>
            <p className="path">{dialog.rootPath ? relativeLibraryPath(dialog.rootPath, dialog.item.library_path) : relativeLibraryPath(dialog.item.path, dialog.item.library_path)}</p>
          </div>
          {dialog.totalSizeBytes !== undefined ? <DirectorySizeTag size={dialog.totalSizeBytes} /> : null}
        </div>
        {loading ? <p className="empty">正在读取文件...</p> : null}
        {dialog.error ? <p className="notice error">{dialog.error}</p> : null}
        {files.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>文件</th>
                  <th>大小</th>
                </tr>
              </thead>
              <tbody>
                {files.map((file) => (
                  <tr key={file.path}>
                    <td className="path">{file.path}</td>
                    <td>{formatBytes(file.size_bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !loading ? (
          <p className="empty">目录下没有文件</p>
        ) : null}
        <div className="dialog-actions">
          <button type="button" className="link-button" onClick={onClose}>
            取消
          </button>
        </div>
      </section>
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
  progress,
  onSkip,
}: {
  dialog: MetadataDialog;
  busy: string | null;
  onChange: (dialog: MetadataDialog) => void;
  onSearch: (dialog: MetadataDialog) => void;
  onApply: (dialog: MetadataDialog) => void;
  onClose: () => void;
  progress?: { current: number; total: number };
  onSkip?: () => void;
}) {
  const searching = busy === `metadata-search:${dialog.item.id}`;
  const applying = busy === `metadata:${dialog.item.id}`;
  const closeDisabled = Boolean(progress && applying);

  return (
    <div className="dialog-backdrop">
      <section className="dialog" role="dialog" aria-modal="true" aria-label="刮削元数据">
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭" disabled={closeDisabled}>
          X
        </button>
        <div className="section-head">
          <div>
            <h2>刮削元数据</h2>
            {progress ? <p className="batch-progress">{progress.current} / {progress.total}</p> : null}
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
          {onSkip ? (
            <button type="button" className="link-button" onClick={onSkip} disabled={searching || applying}>
              跳过
            </button>
          ) : null}
          <button type="button" className="link-button" onClick={onClose} disabled={closeDisabled}>
            {progress ? "取消批量" : "取消"}
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
  progress,
  onSkip,
}: {
  dialog: SubtitleDialog;
  busy: string | null;
  onChange: (dialog: SubtitleDialog) => void;
  onSearch: (dialog: SubtitleDialog) => void;
  onDownload: (dialog: SubtitleDialog) => void;
  onClose: () => void;
  progress?: { current: number; total: number };
  onSkip?: () => void;
}) {
  const searching = busy === `subtitle-search:${dialog.item.id}`;
  const downloading = busy === `subtitle-download:${dialog.item.id}`;
  const closeDisabled = Boolean(progress && downloading);

  return (
    <div className="dialog-backdrop">
      <section className="dialog" role="dialog" aria-modal="true" aria-label="搜索字幕">
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭" disabled={closeDisabled}>
          X
        </button>
        <div className="section-head">
          <div>
            <h2>搜索字幕</h2>
            {progress ? <p className="batch-progress">{progress.current} / {progress.total}</p> : null}
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
          {onSkip ? (
            <button type="button" className="link-button" onClick={onSkip} disabled={searching || downloading}>
              跳过
            </button>
          ) : null}
          <button type="button" className="link-button" onClick={onClose} disabled={closeDisabled}>
            {progress ? "取消批量" : "取消"}
          </button>
        </div>
      </section>
    </div>
  );
}

function BatchSummaryDialog({ summary, onClose }: { summary: BatchSummary; onClose: () => void }) {
  const success = summary.results.filter((result) => result.status === "success").length;
  const failed = summary.results.filter((result) => result.status === "failed").length;
  const skipped = summary.results.filter((result) => result.status === "skipped").length;
  const failures = summary.results.filter((result) => result.status === "failed");

  return (
    <div className="dialog-backdrop">
      <section className="dialog" role="dialog" aria-modal="true" aria-label={summary.title}>
        <button type="button" className="dialog-close" onClick={onClose} aria-label="关闭">
          X
        </button>
        <div className="section-head">
          <h2>{summary.title}</h2>
        </div>
        <div className="batch-counts">
          <span className="good">成功 {success}</span>
          <span className={failed > 0 ? "error" : ""}>失败 {failed}</span>
          <span>跳过 {skipped}</span>
        </div>
        {failures.length > 0 ? (
          <div className="subtitle-results">
            {failures.map((failure, index) => (
              <p key={`${failure.label}:${index}`} className="notice error">
                {failure.label}：{failure.error ?? "操作失败"}
              </p>
            ))}
          </div>
        ) : null}
        <div className="dialog-actions">
          <button type="button" onClick={onClose}>
            确定
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

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = units[0];
  for (const nextUnit of units.slice(1)) {
    if (value < 1024) {
      break;
    }
    value /= 1024;
    unit = nextUnit;
  }
  return `${value >= 10 ? value.toFixed(1) : value.toFixed(2)} ${unit}`;
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

function groupSeriesShows(items: MediaItem[]) {
  const shows = new Map<string, SeriesSummary>();
  for (const item of items) {
    const seasonNumber = item.season ?? 1;
    const showPath = seriesDirectoryPath(item);
    const key = [item.title, item.year ?? "", showPath].join("\u0000");
    const current = shows.get(key);
    if (current) {
      current.items.push(item);
      if (!current.seasons.includes(seasonNumber)) {
        current.seasons.push(seasonNumber);
      }
      current.subtitles.push(...(item.subtitles ?? []));
      current.missingNfo += item.has_nfo ? 0 : 1;
      current.hasMetadata ||= item.has_metadata;
      current.renameNeeded ||= item.rename_needed;
      current.missingSubtitles += (item.subtitles ?? []).length === 0 ? 1 : 0;
      continue;
    }
    shows.set(key, {
      key,
      title: item.title,
      year: item.year,
      seasons: [seasonNumber],
      items: [item],
      representative: item,
      path: showPath,
      subtitles: [...(item.subtitles ?? [])],
      missingNfo: item.has_nfo ? 0 : 1,
      hasMetadata: item.has_metadata,
      renameNeeded: item.rename_needed,
      missingSubtitles: (item.subtitles ?? []).length === 0 ? 1 : 0,
      directorySizeBytes: item.directory_size_bytes ?? 0,
    });
  }
  const result = [...shows.values()];
  for (const show of result) {
    show.seasons.sort((left, right) => left - right);
    show.items.sort(compareEpisodes);
  }
  return result.sort((left, right) => mediaTitle(left).localeCompare(mediaTitle(right), "zh-CN"));
}

function matchesIssues(filters: IssueFilter[], issues: { hasMetadata: boolean; missingSubtitles: boolean; renameNeeded: boolean }) {
  if (filters.length === 0) {
    return true;
  }
  return filters.some((filter) => {
    if (filter === "missing-metadata") {
      return !issues.hasMetadata;
    }
    if (filter === "missing-subtitles") {
      return issues.missingSubtitles;
    }
    return issues.renameNeeded;
  });
}

function mediaMatchesIssues(item: MediaItem, filters: IssueFilter[]) {
  return matchesIssues(filters, {
    hasMetadata: item.has_metadata,
    missingSubtitles: (item.subtitles ?? []).length === 0,
    renameNeeded: item.rename_needed,
  });
}

function seriesMatchesIssues(show: SeriesSummary, filters: IssueFilter[]) {
  return matchesIssues(filters, {
    hasMetadata: show.hasMetadata,
    missingSubtitles: show.missingSubtitles > 0,
    renameNeeded: show.renameNeeded,
  });
}

function mediaTitle(item: Pick<MediaItem, "title" | "year">) {
  return item.year ? `${item.title} (${item.year})` : item.title;
}

function compareEpisodes(left: MediaItem, right: MediaItem) {
  return (left.season ?? 0) - (right.season ?? 0) || (left.episode ?? 0) - (right.episode ?? 0) || left.path.localeCompare(right.path);
}

function guidedBatchLabel(kind: GuidedBatchKind, item: MediaItem) {
  if (kind === "subtitle" && item.season !== undefined && item.episode !== undefined) {
    return `${mediaTitle(item)} S${pad(item.season)}E${pad(item.episode)}`;
  }
  return mediaTitle(item);
}

function guidedBatchSummaryTitle(kind: GuidedBatchKind) {
  return kind === "metadata" ? "批量刮削结果" : "批量字幕结果";
}

function nfoLabel(summary: Pick<SeriesSummary, "items" | "missingNfo">) {
  if (summary.missingNfo === 0) {
    return "已有";
  }
  if (summary.missingNfo === summary.items.length) {
    return "缺失";
  }
  return `${summary.items.length - summary.missingNfo}/${summary.items.length}`;
}

function seasonCountLabel(show: Pick<SeriesSummary, "seasons">) {
  if (show.seasons.length === 1) {
    return `第 ${pad(show.seasons[0])} 季`;
  }
  return `${show.seasons.length} 季`;
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

function seriesDirectoryPath(item: MediaItem) {
  const relative = relativeLibraryPath(item.path, item.library_path).replaceAll("\\", "/");
  const showDirectory = relative.split("/")[0];
  return `${item.library_path.replace(/[/\\]+$/, "")}/${showDirectory}`;
}

function isSeriesBatchTarget(target: BatchTarget) {
  return target.item.kind === "series";
}

function markDuplicateRenameTargets(entries: BatchRenameEntry[]) {
  const indexesByTarget = new Map<string, Set<number>>();
  entries.forEach((entry, index) => {
    if (!entry.preview || entry.error) {
      return;
    }
    for (const change of new Set(renameChanges(entry.preview).map((item) => item.to))) {
      const indexes = indexesByTarget.get(change) ?? new Set<number>();
      indexes.add(index);
      indexesByTarget.set(change, indexes);
    }
  });
  const duplicateIndexes = new Set<number>();
  for (const indexes of indexesByTarget.values()) {
    if (indexes.size > 1) {
      indexes.forEach((index) => duplicateIndexes.add(index));
    }
  }
  if (duplicateIndexes.size === 0) {
    return entries;
  }
  return entries.map((entry, index) => {
    if (!entry.preview || !duplicateIndexes.has(index)) {
      return entry;
    }
    return {
      ...entry,
      preview: {
        ...entry.preview,
        can_apply: false,
        conflicts: [...new Set([...entry.preview.conflicts, "duplicate_target"])],
      },
    };
  });
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

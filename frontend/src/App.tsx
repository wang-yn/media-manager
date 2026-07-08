import { useEffect, useMemo, useState } from "react";

type Health = {
  status: string;
  config: string;
  media_dir: string;
};

type Source = {
  name: string;
  enabled: boolean;
  priority: number;
  root_url?: string;
  daily_download_limit?: number;
  languages?: string[];
};

type Config = {
  libraries?: Array<{ name: string; kind: string; path: string }>;
  metadata_sources?: Source[];
  subtitle_sources?: Source[];
};

type MediaItem = {
  kind: string;
  title: string;
  path: string;
  library: string;
  year?: number;
  season?: number;
  episode?: number;
  subtitles?: string[];
};

type Scan = {
  count: number;
  items: MediaItem[];
};

const emptyScan: Scan = { count: 0, items: [] };

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [config, setConfig] = useState<Config>({});
  const [scan, setScan] = useState<Scan>(emptyScan);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [healthRes, configRes, scanRes] = await Promise.all([
        fetch("/api/health"),
        fetch("/api/config"),
        fetch("/api/scan"),
      ]);
      if (!healthRes.ok || !configRes.ok || !scanRes.ok) {
        throw new Error("API 返回异常");
      }
      setHealth(await healthRes.json());
      setConfig(await configRes.json());
      setScan(await scanRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法连接后端");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const sources = useMemo(
    () => [...(config.metadata_sources ?? []), ...(config.subtitle_sources ?? [])].sort((a, b) => a.priority - b.priority),
    [config],
  );

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Media Manager</p>
          <h1>影视媒体库工作台</h1>
        </div>
        <button type="button" onClick={refresh} disabled={loading}>
          {loading ? "刷新中" : "刷新"}
        </button>
      </header>

      {error ? <p className="notice error">{error}</p> : null}

      <section className="summary" aria-label="系统状态">
        <Status label="后端" value={health?.status ?? "unknown"} tone={health?.status === "ok" ? "good" : "warn"} />
        <Status label="配置" value={health?.config ?? "-"} />
        <Status label="媒体目录" value={health?.media_dir ?? "-"} />
        <Status label="已发现" value={`${scan.count} 个视频`} tone={scan.count > 0 ? "good" : "warn"} />
      </section>

      <section className="layout">
        <div className="panel">
          <div className="section-head">
            <h2>媒体库</h2>
          </div>
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>类型</th>
                <th>路径</th>
              </tr>
            </thead>
            <tbody>
              {(config.libraries ?? []).map((library) => (
                <tr key={`${library.kind}:${library.path}`}>
                  <td>{library.name}</td>
                  <td>{library.kind}</td>
                  <td className="path">{library.path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <div className="section-head">
            <h2>来源</h2>
          </div>
          <div className="source-list">
            {sources.map((source) => (
              <article className="source" key={source.name}>
                <div>
                  <strong>{source.name}</strong>
                  <span>{source.root_url ?? "local"}</span>
                </div>
                <small className={source.enabled ? "enabled" : "disabled"}>{source.enabled ? "启用" : "停用"}</small>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>扫描结果</h2>
          <span>{loading ? "读取中" : `${scan.count} 项`}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>标题</th>
                <th>类型</th>
                <th>季/集</th>
                <th>字幕</th>
                <th>路径</th>
              </tr>
            </thead>
            <tbody>
              {scan.items.map((item) => (
                <tr key={item.path}>
                  <td>{item.year ? `${item.title} (${item.year})` : item.title}</td>
                  <td>{item.kind}</td>
                  <td>{item.season && item.episode ? `S${pad(item.season)}E${pad(item.episode)}` : "-"}</td>
                  <td>{item.subtitles?.length ?? 0}</td>
                  <td className="path">{item.path}</td>
                </tr>
              ))}
              {!loading && scan.items.length === 0 ? (
                <tr>
                  <td colSpan={5} className="empty">
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

function Status({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" }) {
  return (
    <div className="status">
      <span>{label}</span>
      <strong className={tone ?? ""}>{value}</strong>
    </div>
  );
}

function pad(value: number) {
  return String(value).padStart(2, "0");
}

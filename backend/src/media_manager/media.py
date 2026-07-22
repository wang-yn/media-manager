from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path
import os
import re


VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa"}
IGNORED_DIRS = {".@__thumb"}
SMALL_VIDEO_BYTES = 100 * 1024 * 1024
SIDECAR_EXTENSIONS = {".nfo", *SUBTITLE_EXTENSIONS}
EPISODE_RE = re.compile(r"[Ss](?P<season>\d{1,2})[ ._-]?[Ee](?P<episode>\d{1,3})")
SEASON_DIR_RE = re.compile(r"(?:season|s)[ ._-]?(?P<season>\d{1,2})", re.IGNORECASE)
YEAR_RE = re.compile(r"(?:^|[ ._\-(])(?P<year>19\d{2}|20\d{2})(?:$|[ ._\-)])")
STRICT_YEAR_RE = re.compile(r"\((?:19\d{2}|20\d{2})\)")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")
STRICT_SEASON_DIR_RE = re.compile(r"^Season (?P<season>\d{2})$")
RELEASE_MARKERS = {
    "amzn",
    "bdrip",
    "bluray",
    "brrip",
    "dsnp",
    "dvdrip",
    "hdtv",
    "hdrip",
    "max",
    "nf",
    "web",
    "web-dl",
    "webrip",
}


@dataclass(frozen=True)
class MediaItem:
    kind: str
    title: str
    path: str
    library: str
    library_path: str
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    subtitles: list[str] | None = None
    nfo_path: str | None = None
    has_nfo: bool = False
    has_metadata: bool = False
    directory_size_bytes: int = 0
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", sha1(self.path.encode("utf-8")).hexdigest()[:16])
        if self.nfo_path is None:
            object.__setattr__(self, "nfo_path", str(_nfo_path(self)))
        object.__setattr__(self, "has_nfo", bool(self.nfo_path and Path(self.nfo_path).exists()))
        metadata_path = _metadata_path(self)
        object.__setattr__(self, "has_metadata", bool(metadata_path and metadata_path.exists()))

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value not in (None, [])}


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


def scan_libraries(libraries: list[object]) -> list[MediaItem]:
    items: list[MediaItem] = []
    for library in libraries:
        root = Path(library.path)
        if not root.exists():
            continue
        for video in sorted(_video_files(root)):
            if library.kind == "series":
                items.append(_series_item(root, video, library.name))
            elif library.kind == "movie":
                items.append(_movie_item(root, video, library.name))
            else:
                items.append(_unknown_item(video, library.name))
    return items


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
    return AuditIssue(
        type=issue_type,
        message=message,
        library=library_name,
        relative_path=_relative_path(root, path),
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


def _video_files(root: Path) -> list[Path]:
    return [path for path in _walk_files(root) if path.suffix.lower() in VIDEO_EXTENSIONS]


def _movie_item(root: Path, video: Path, library_name: str) -> MediaItem:
    title_source = video.parent.name if video.parent != root else video.stem
    return MediaItem(
        kind="movie",
        title=_clean_title(title_source),
        year=_year(title_source) or _year(video.stem),
        path=str(video),
        library=library_name,
        library_path=str(root),
        subtitles=_sidecar_subtitles(video),
        directory_size_bytes=directory_size(video.parent),
    )


def _series_item(root: Path, video: Path, library_name: str) -> MediaItem:
    relative = video.relative_to(root)
    show_title = relative.parts[0] if len(relative.parts) > 1 else video.stem
    show_dir = root / relative.parts[0] if len(relative.parts) > 1 else video.parent
    match = EPISODE_RE.search(video.stem)
    season = int(match.group("season")) if match else _season_from_dirs(video)
    episode = int(match.group("episode")) if match else None
    return MediaItem(
        kind="series",
        title=_clean_title(show_title),
        year=_year(show_title),
        season=season,
        episode=episode,
        path=str(video),
        library=library_name,
        library_path=str(root),
        subtitles=_sidecar_subtitles(video),
        directory_size_bytes=directory_size(show_dir),
    )


def _unknown_item(video: Path, library_name: str) -> MediaItem:
    return MediaItem(kind="unknown", title=_clean_title(video.stem), path=str(video), library=library_name, library_path=str(video.parent), directory_size_bytes=directory_size(video.parent))


def _clean_title(value: str) -> str:
    value = YEAR_RE.sub(" ", value)
    value = re.sub(r"[._]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    tokens: list[str] = []
    for token in value.strip(" -").split():
        if _release_marker(token):
            break
        tokens.append(token)
    return " ".join(tokens).strip(" -")


def _release_marker(token: str) -> bool:
    token = token.strip(" -[]()").lower()
    return (
        bool(re.fullmatch(r"s\d{1,2}", token))
        or bool(re.fullmatch(r"\d{3,4}p", token))
        or bool(re.fullmatch(r"[xh]26[45]", token))
        or token.startswith(("ddp", "dts"))
        or token in RELEASE_MARKERS
    )


def _year(value: str) -> int | None:
    match = YEAR_RE.search(value)
    return int(match.group("year")) if match else None


def _season_from_dirs(video: Path) -> int | None:
    for parent in video.parents:
        match = SEASON_DIR_RE.search(parent.name)
        if match:
            return int(match.group("season"))
    return None


def _sidecar_subtitles(video: Path) -> list[str]:
    return [
        str(path)
        for path in sorted(video.parent.iterdir())
        if path.is_file() and path.name.startswith(video.stem) and path.suffix.lower() in SUBTITLE_EXTENSIONS
    ]


def directory_size(root: Path) -> int:
    return sum(file.stat().st_size for file in _walk_files(root))


def directory_files(root: Path) -> list[dict[str, object]]:
    return [{"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size} for path in sorted(_walk_files(root))]


def _walk_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        files.extend(Path(current) / name for name in names)
    return files


def _nfo_path(item: MediaItem) -> Path:
    video = Path(item.path)
    if item.kind == "movie":
        return _movie_nfo_path(video)
    return video.with_suffix(".nfo")


def _metadata_path(item: MediaItem) -> Path | None:
    video = Path(item.path)
    if item.kind == "movie":
        return _movie_nfo_path(video)
    if item.kind != "series":
        return None
    library = Path(item.library_path)
    try:
        show_name = video.relative_to(library).parts[0]
    except (ValueError, IndexError):
        return video.parents[1] / "tvshow.nfo"
    return library / show_name / "tvshow.nfo"


def _movie_nfo_path(video: Path) -> Path:
    filename_nfo = video.with_suffix(".nfo")
    if filename_nfo.exists():
        return filename_nfo
    movie_nfo = video.parent / "movie.nfo"
    if movie_nfo.exists():
        return movie_nfo
    return filename_nfo

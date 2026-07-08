from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path
import re


VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa"}
EPISODE_RE = re.compile(r"[Ss](?P<season>\d{1,2})[ ._-]?[Ee](?P<episode>\d{1,3})")
SEASON_DIR_RE = re.compile(r"(?:season|s)[ ._-]?(?P<season>\d{1,2})", re.IGNORECASE)
YEAR_RE = re.compile(r"(?:^|[ ._\-(])(?P<year>19\d{2}|20\d{2})(?:$|[ ._\-)])")


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
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", sha1(self.path.encode("utf-8")).hexdigest()[:16])
        if self.nfo_path is None:
            object.__setattr__(self, "nfo_path", str(_nfo_path(self)))
        object.__setattr__(self, "has_nfo", bool(self.nfo_path and Path(self.nfo_path).exists()))

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value not in (None, [])}


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


def _video_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]


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
    )


def _series_item(root: Path, video: Path, library_name: str) -> MediaItem:
    relative = video.relative_to(root)
    show_title = relative.parts[0] if len(relative.parts) > 1 else video.stem
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
    )


def _unknown_item(video: Path, library_name: str) -> MediaItem:
    return MediaItem(kind="unknown", title=_clean_title(video.stem), path=str(video), library=library_name, library_path=str(video.parent))


def _clean_title(value: str) -> str:
    value = YEAR_RE.sub(" ", value)
    value = re.sub(r"[._]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -")


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
        for path in sorted(video.parent.glob(f"{video.stem}*"))
        if path.is_file() and path.suffix.lower() in SUBTITLE_EXTENSIONS
    ]


def _nfo_path(item: MediaItem) -> Path:
    video = Path(item.path)
    if item.kind == "movie":
        return video.parent / "movie.nfo"
    return video.with_suffix(".nfo")

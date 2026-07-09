from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from .errors import AppError
from .media import MediaItem


RenameChange = TypedDict("RenameChange", {"from": str, "to": str})


class RenamePreview(TypedDict):
    can_apply: bool
    conflicts: list[str]
    changes: list[RenameChange]


class RenameApplyResult(TypedDict):
    changes: list[RenameChange]


def preview_rename(item: MediaItem) -> RenamePreview:
    changes = _changes(item)
    conflicts: list[str] = []
    targets: set[Path] = set()
    library = Path(item.library_path).resolve()
    for change in changes:
        target = Path(change["to"]).resolve()
        if not target.is_relative_to(library):
            conflicts.append("outside_library")
        if target.exists() and target != Path(change["from"]).resolve():
            conflicts.append("target_exists")
        if target in targets:
            conflicts.append("duplicate_target")
        targets.add(target)
    conflicts = sorted(set(conflicts))
    return {"can_apply": not conflicts, "conflicts": conflicts, "changes": changes}


def apply_rename(item: MediaItem) -> RenameApplyResult:
    preview = preview_rename(item)
    if not preview["can_apply"]:
        raise AppError("rename_conflict", "重命名存在冲突", ", ".join(preview["conflicts"]), item.path)
    changes = list(preview["changes"])
    try:
        for change in changes:
            source = Path(change["from"])
            target = Path(change["to"])
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                source.rename(target)
        _cleanup_empty_dirs(Path(item.path).parent, Path(item.library_path))
    except OSError as exc:
        raise AppError("rename_failed", "重命名失败", str(exc), item.path) from exc
    return {"changes": changes}


def _changes(item: MediaItem) -> list[RenameChange]:
    video = Path(item.path)
    target_video = _target_video(item)
    changes: list[RenameChange] = [{"from": str(video), "to": str(target_video)}]
    for sidecar in sorted(video.parent.glob(f"{video.stem}*")):
        if sidecar == video or not sidecar.is_file():
            continue
        if sidecar.suffix.lower() not in {".srt", ".ass", ".ssa", ".nfo"}:
            continue
        suffix = sidecar.name.removeprefix(video.stem)
        changes.append({"from": str(sidecar), "to": str(target_video.with_name(target_video.stem + suffix))})
    movie_nfo = video.parent / "movie.nfo"
    if item.kind == "movie" and movie_nfo.exists() and movie_nfo.parent != target_video.parent:
        changes.append({"from": str(movie_nfo), "to": str(target_video.parent / "movie.nfo")})
    return changes


def _target_video(item: MediaItem) -> Path:
    video = Path(item.path)
    library = Path(item.library_path)
    extension = video.suffix
    if item.kind == "movie":
        name = item.title if item.year is None else f"{item.title} ({item.year})"
        return library / name / f"{name}{extension}"
    if item.kind == "series":
        season = item.season or 1
        episode = item.episode or 1
        show_dir = library / item.title
        return show_dir / f"Season {season:02d}" / f"{item.title} - S{season:02d}E{episode:02d}{extension}"
    return video


def _cleanup_empty_dirs(start: Path, stop: Path) -> None:
    stop = stop.resolve()
    current = start
    while current.resolve().is_relative_to(stop) and current.resolve() != stop:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent

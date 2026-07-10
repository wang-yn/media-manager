from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict
import xml.etree.ElementTree as ET

from .errors import AppError
from .media import MediaItem


RenameChange = TypedDict("RenameChange", {"from": str, "to": str})


class RenamePreview(TypedDict):
    can_apply: bool
    conflicts: list[str]
    changes: list[RenameChange]


class RenameApplyResult(TypedDict):
    changes: list[RenameChange]


class RenameName(TypedDict):
    display: str
    year: int | None


def _target_name(item: MediaItem, nfo: Path) -> RenameName:
    title, original, year = _nfo_values(nfo)
    display = _join_titles(original, title) if title and original else item.title
    return {"display": display, "year": year or item.year}


def _nfo_values(path: Path) -> tuple[str, str, int | None]:
    if not path.exists():
        return "", "", None
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return "", "", None
    title = (root.findtext("title") or "").strip()
    original = (root.findtext("originaltitle") or "").strip()
    year_text = (root.findtext("year") or "").strip()
    return title, original, int(year_text) if year_text.isdigit() else None


def _join_titles(original: str, local: str) -> str:
    if original and local and original != local:
        return f"{original} - {local}"
    return original or local


def _with_year(name: str, year: int | None) -> str:
    return f"{name} ({year})" if year else name


def preview_rename(item: MediaItem) -> RenamePreview:
    return _preview_changes(_changes(item), Path(item.library_path))


def apply_rename(item: MediaItem) -> RenameApplyResult:
    preview = preview_rename(item)
    if not preview["can_apply"]:
        raise AppError("rename_conflict", "重命名存在冲突", ", ".join(preview["conflicts"]), item.path)
    changes = list(preview["changes"])
    _apply_changes(changes, [Path(item.path).parent], Path(item.library_path), item.path)
    return {"changes": changes}


def preview_batch_rename(items: list[MediaItem]) -> RenamePreview:
    if not items:
        return {"can_apply": True, "conflicts": [], "changes": []}
    return _preview_changes(_dedupe_changes(change for item in items for change in _changes(item)), Path(items[0].library_path))


def apply_batch_rename(items: list[MediaItem]) -> RenameApplyResult:
    if not items:
        return {"changes": []}
    preview = preview_batch_rename(items)
    if not preview["can_apply"]:
        detail = ", ".join(preview["conflicts"])
        raise AppError("rename_conflict", "批量重命名存在冲突", detail, items[0].path if items else None)
    changes = list(preview["changes"])
    _apply_changes(changes, [Path(item.path).parent for item in items], Path(items[0].library_path), items[0].path if items else "")
    return {"changes": changes}


def _preview_changes(changes: list[RenameChange], library: Path) -> RenamePreview:
    conflicts: list[str] = []
    targets: set[Path] = set()
    library = library.resolve()
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


def _apply_changes(changes: list[RenameChange], cleanup_starts: list[Path], library: Path, error_path: str) -> None:
    try:
        for change in changes:
            source = Path(change["from"])
            target = Path(change["to"])
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                source.rename(target)
        for start in sorted(set(cleanup_starts), key=lambda path: len(path.parts), reverse=True):
            _cleanup_empty_dirs(start, library)
    except OSError as exc:
        raise AppError("rename_failed", "重命名失败", str(exc), error_path) from exc


def _dedupe_changes(changes: Iterable[RenameChange]) -> list[RenameChange]:
    result: list[RenameChange] = []
    seen: set[tuple[str, str]] = set()
    for change in changes:
        key = (change["from"], change["to"])
        if key in seen:
            continue
        seen.add(key)
        result.append(change)
    return result


def _changes(item: MediaItem) -> list[RenameChange]:
    video = Path(item.path)
    target_video = _target_video(item)
    changes: list[RenameChange] = [{"from": str(video), "to": str(target_video)}]
    for sidecar in sorted(video.parent.iterdir()):
        if sidecar == video or not sidecar.is_file():
            continue
        if not sidecar.name.startswith(video.stem):
            continue
        if sidecar.suffix.lower() not in {".srt", ".ass", ".ssa", ".nfo"}:
            continue
        suffix = sidecar.name.removeprefix(video.stem)
        changes.append({"from": str(sidecar), "to": str(target_video.with_name(target_video.stem + suffix))})
    movie_nfo = video.parent / "movie.nfo"
    if item.kind == "movie" and movie_nfo.exists() and movie_nfo.parent != target_video.parent:
        changes.append({"from": str(movie_nfo), "to": str(target_video.parent / "movie.nfo")})
    if item.kind == "series":
        tvshow_nfo = _show_dir(item) / "tvshow.nfo"
        if tvshow_nfo.exists() and tvshow_nfo.parent != target_video.parents[1]:
            changes.append({"from": str(tvshow_nfo), "to": str(target_video.parents[1] / "tvshow.nfo")})
    return changes


def _show_dir(item: MediaItem) -> Path:
    video = Path(item.path)
    library = Path(item.library_path)
    try:
        first = video.relative_to(library).parts[0]
    except (ValueError, IndexError):
        return video.parents[1]
    return library / first


def _target_video(item: MediaItem) -> Path:
    video = Path(item.path)
    library = Path(item.library_path)
    extension = video.suffix
    if item.kind == "movie":
        target = _target_name(item, video.parent / "movie.nfo")
        name = _with_year(target["display"], target["year"])
        return library / name / f"{name}{extension}"
    if item.kind == "series":
        season = item.season or 1
        episode = item.episode or 1
        target = _target_name(item, _show_dir(item) / "tvshow.nfo")
        show_name = _with_year(target["display"], target["year"])
        file_name = f'{target["display"]} - S{season:02d}E{episode:02d}'
        return library / show_name / f"Season {season:02d}" / f"{file_name}{extension}"
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

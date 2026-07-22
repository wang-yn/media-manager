from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from .errors import AppError
from .media import MediaItem


def write_nfo(item: MediaItem, metadata: dict[str, object]) -> Path:
    try:
        if item.kind == "movie":
            return _write_movie(item, metadata)
        if item.kind == "series":
            _write_show(item, metadata)
            return _write_episode(item, metadata)
    except OSError as exc:
        raise AppError("nfo_write_failed", "写入 NFO 失败", str(exc), item.path) from exc
    raise AppError("nfo_write_failed", "未知媒体类型无法写入 NFO", item.kind, item.path)


def _write_movie(item: MediaItem, metadata: dict[str, object]) -> Path:
    target = Path(item.path).with_suffix(".nfo")
    root = ET.Element("movie")
    _basic_fields(root, metadata, item)
    return _write_xml(target, root)


def _write_show(item: MediaItem, metadata: dict[str, object]) -> Path:
    target = _show_dir(item) / "tvshow.nfo"
    root = ET.Element("tvshow")
    _basic_fields(root, metadata, item)
    return _write_xml(target, root)


def _write_episode(item: MediaItem, metadata: dict[str, object]) -> Path:
    target = Path(item.path).with_suffix(".nfo")
    root = ET.Element("episodedetails")
    _basic_fields(root, metadata, item)
    if item.season is not None:
        ET.SubElement(root, "season").text = str(item.season)
    if item.episode is not None:
        ET.SubElement(root, "episode").text = str(item.episode)
    return _write_xml(target, root)


def _basic_fields(root: ET.Element, metadata: dict[str, object], item: MediaItem) -> None:
    title = metadata.get("title") or metadata.get("name") or item.title
    original = metadata.get("original_title") or metadata.get("original_name")
    year = _year(metadata) or item.year
    ET.SubElement(root, "title").text = str(title)
    if original:
        ET.SubElement(root, "originaltitle").text = str(original)
    if metadata.get("english_title"):
        ET.SubElement(root, "englishtitle").text = str(metadata["english_title"])
    if year:
        ET.SubElement(root, "year").text = str(year)
    if metadata.get("overview"):
        ET.SubElement(root, "plot").text = str(metadata["overview"])
    if metadata.get("id"):
        ET.SubElement(root, "tmdbid").text = str(metadata["id"])
    ET.SubElement(root, "type").text = item.kind


def _write_xml(target: Path, root: ET.Element) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)
    return target


def _show_dir(item: MediaItem) -> Path:
    video = Path(item.path)
    library = Path(item.library_path)
    try:
        first = video.relative_to(library).parts[0]
    except ValueError:
        return video.parents[1]
    return library / first


def _year(metadata: dict[str, object]) -> int | None:
    value = str(metadata.get("release_date") or metadata.get("first_air_date") or "")
    if len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    return None

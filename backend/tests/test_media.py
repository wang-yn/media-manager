from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from media_manager.media import scan_libraries


@dataclass(frozen=True)
class Library:
    name: str
    kind: str
    path: Path


class ScanLibrariesTest(unittest.TestCase):
    def test_scans_movies_and_series(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
            episode = root / "tv" / "Pantheon (2022)" / "Season 01" / "Pantheon - S01E03 - Reign of Winter.mkv"
            subtitle = episode.with_suffix(".chs.ass")
            movie.parent.mkdir(parents=True)
            episode.parent.mkdir(parents=True)
            movie.write_text("", encoding="utf-8")
            episode.write_text("", encoding="utf-8")
            subtitle.write_text("", encoding="utf-8")

            items = scan_libraries(
                [
                    Library("Movies", "movie", root / "movies"),
                    Library("TV Shows", "series", root / "tv"),
                ]
            )

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].kind, "movie")
        self.assertEqual(items[0].title, "Dune")
        self.assertEqual(items[0].year, 2021)
        self.assertEqual(items[1].kind, "series")
        self.assertEqual(items[1].title, "Pantheon")
        self.assertEqual(items[1].season, 1)
        self.assertEqual(items[1].episode, 3)
        self.assertEqual(len(items[1].subtitles or []), 1)
        self.assertTrue(items[0].id)
        self.assertTrue(items[1].id)
        self.assertEqual(items[0].library_path, str(root / "movies"))
        self.assertEqual(items[1].library_path, str(root / "tv"))
        self.assertEqual(items[0].nfo_path, str(movie.parent / "movie.nfo"))
        self.assertEqual(items[1].nfo_path, str(episode.with_suffix(".nfo")))
        self.assertFalse(items[0].has_nfo)
        self.assertFalse(items[1].has_nfo)

    def test_marks_existing_nfo(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
            nfo = movie.parent / "movie.nfo"
            movie.parent.mkdir(parents=True)
            movie.write_text("", encoding="utf-8")
            nfo.write_text("<movie />", encoding="utf-8")

            items = scan_libraries([Library("Movies", "movie", root / "movies")])

        self.assertEqual(items[0].nfo_path, str(nfo))
        self.assertTrue(items[0].has_nfo)

    def test_finds_sidecar_subtitles_when_name_contains_glob_characters(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = root / "movies" / "Dune [1080p]" / "Dune [1080p].mkv"
            subtitle = movie.with_suffix(".srt")
            movie.parent.mkdir(parents=True)
            movie.write_text("", encoding="utf-8")
            subtitle.write_text("", encoding="utf-8")

            items = scan_libraries([Library("Movies", "movie", root / "movies")])

        self.assertEqual(items[0].subtitles, [str(subtitle)])


if __name__ == "__main__":
    unittest.main()

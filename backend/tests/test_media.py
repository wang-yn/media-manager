from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from media_manager.media import MediaItem, audit_libraries, scan_libraries


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
        self.assertFalse(items[0].has_metadata)
        self.assertFalse(items[1].has_metadata)

    def test_marks_movie_and_series_media_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
            episode = root / "tv" / "Pantheon (2022)" / "Season 01" / "Pantheon - S01E03.mkv"
            movie_nfo = movie.parent / "movie.nfo"
            series_nfo = root / "tv" / "Pantheon (2022)" / "tvshow.nfo"
            movie.parent.mkdir(parents=True)
            episode.parent.mkdir(parents=True)
            movie.write_text("", encoding="utf-8")
            episode.write_text("", encoding="utf-8")
            movie_nfo.write_text("<movie />", encoding="utf-8")
            series_nfo.write_text("<tvshow />", encoding="utf-8")

            items = scan_libraries(
                [
                    Library("Movies", "movie", root / "movies"),
                    Library("TV", "series", root / "tv"),
                ]
            )

        movie_item, series_item = items
        self.assertTrue(movie_item.has_metadata)
        self.assertTrue(series_item.has_metadata)
        self.assertTrue(movie_item.has_nfo)
        self.assertFalse(series_item.has_nfo)
        self.assertTrue(movie_item.to_dict()["has_metadata"])
        self.assertTrue(series_item.to_dict()["has_metadata"])

    def test_series_metadata_falls_back_when_library_relative_path_has_no_show(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "configured-tv-library"
            video = root / "other" / "Pantheon (2022)" / "Season 01" / "Pantheon - S01E03.mkv"
            fallback_nfo = video.parents[1] / "tvshow.nfo"
            library.mkdir(parents=True)
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            fallback_nfo.write_text("<tvshow />", encoding="utf-8")

            item = MediaItem(
                kind="series",
                title="Pantheon",
                path=str(video),
                library="TV",
                library_path=str(library),
            )

        self.assertTrue(item.has_metadata)

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

    def test_marks_movie_filename_nfo(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
            nfo = movie.with_suffix(".nfo")
            movie.parent.mkdir(parents=True)
            movie.write_text("", encoding="utf-8")
            nfo.write_text("<movie />", encoding="utf-8")

            items = scan_libraries([Library("Movies", "movie", root / "movies")])

        self.assertEqual(items[0].nfo_path, str(nfo))
        self.assertTrue(items[0].has_nfo)
        self.assertTrue(items[0].has_metadata)

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

    def test_reports_media_directory_size(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
            poster = movie.parent / "poster.jpg"
            thumb = movie.parent / ".@__thumb" / "cached.mkv"
            movie.parent.mkdir(parents=True)
            thumb.parent.mkdir()
            movie.write_bytes(b"video")
            poster.write_bytes(b"poster")
            thumb.write_bytes(b"ignored")

            items = scan_libraries([Library("Movies", "movie", root / "movies")])

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].directory_size_bytes, 11)
        self.assertEqual(items[0].to_dict()["directory_size_bytes"], 11)

    def test_cleans_common_movie_release_names(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            matrix = (
                root
                / "movies"
                / "The.Matrix.1999.1080p.BluRay.x264.DTS-FGT"
                / "The.Matrix.1999.1080p.BluRay.x264.DTS-FGT.mkv"
            )
            dune = (
                root
                / "movies"
                / "Dune.Part.Two.2024.2160p.WEB-DL.DDP5.1.Atmos.H.265-GROUP"
                / "Dune.Part.Two.2024.2160p.WEB-DL.DDP5.1.Atmos.H.265-GROUP.mp4"
            )
            matrix.parent.mkdir(parents=True)
            dune.parent.mkdir(parents=True)
            matrix.write_text("", encoding="utf-8")
            dune.write_text("", encoding="utf-8")

            items = scan_libraries([Library("Movies", "movie", root / "movies")])

        by_year = {item.year: item for item in items}
        self.assertEqual(by_year[1999].title, "The Matrix")
        self.assertEqual(by_year[2024].title, "Dune Part Two")

    def test_cleans_common_series_release_names(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            last_of_us = (
                root
                / "tv"
                / "The.Last.of.Us.S01.1080p.WEB-DL"
                / "Season 01"
                / "The.Last.of.Us.S01E02.Infected.1080p.WEB.H264-GROUP.mkv"
            )
            fallout = (
                root
                / "tv"
                / "Fallout.2024.S01.2160p.AMZN.WEB-DL"
                / "Season 01"
                / "Fallout.2024.S01E01.The.End.2160p.AMZN.WEB-DL.DDP5.1.H.265-GROUP.avi"
            )
            last_of_us.parent.mkdir(parents=True)
            fallout.parent.mkdir(parents=True)
            last_of_us.write_text("", encoding="utf-8")
            fallout.write_text("", encoding="utf-8")

            items = scan_libraries([Library("TV Shows", "series", root / "tv")])

        by_episode = {(item.season, item.episode): item for item in items}
        self.assertEqual(by_episode[(1, 1)].title, "Fallout")
        self.assertEqual(by_episode[(1, 1)].year, 2024)
        self.assertEqual(by_episode[(1, 2)].title, "The Last of Us")
        self.assertIsNone(by_episode[(1, 2)].year)

    def test_audit_libraries_reports_quality_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movies = root / "movies"
            tv = root / "tv"

            (movies / "Empty").mkdir(parents=True)
            (movies / "Images Only").mkdir(parents=True)
            (movies / "Images Only" / "poster.jpg").write_bytes(b"poster")
            (movies / "Loose.Movie.2024.mkv").write_bytes(b"x")
            (movies / "Bad Movie").mkdir(parents=True)
            (movies / "Bad Movie" / "Bad Movie.mkv").write_bytes(b"x")
            (movies / "Orphans").mkdir(parents=True)
            (movies / "Orphans" / "lost.srt").write_text("subtitle", encoding="utf-8")
            (movies / ".@__thumb").mkdir(parents=True)
            (movies / ".@__thumb" / "ignored.srt").write_text("ignored", encoding="utf-8")
            ok_movie = movies / "沙丘 Dune (2021)" / "沙丘 Dune (2021).mkv"
            ok_movie.parent.mkdir(parents=True)
            with ok_movie.open("wb") as file:
                file.truncate(105 * 1024 * 1024)

            (tv / "Root.Show.S01E01.mkv").parent.mkdir(parents=True, exist_ok=True)
            (tv / "Root.Show.S01E01.mkv").write_bytes(b"x")
            missing_season = tv / "Pantheon (2022)" / "Pantheon - S01E03.mkv"
            missing_season.parent.mkdir(parents=True)
            missing_season.write_bytes(b"x")
            bad_season = tv / "Good Show (2024)" / "Season One" / "Good Show - S01E01.mkv"
            bad_season.parent.mkdir(parents=True)
            bad_season.write_bytes(b"x")
            bad_episode = tv / "Another Show (2024)" / "Season 01" / "Another Show - Episode 01.mkv"
            bad_episode.parent.mkdir(parents=True)
            bad_episode.write_bytes(b"x")
            ok_episode = tv / "Valid Show (2024)" / "Season 01" / "Valid Show - S01E01.mkv"
            ok_episode.parent.mkdir(parents=True)
            with ok_episode.open("wb") as file:
                file.truncate(105 * 1024 * 1024)

            results = audit_libraries(
                [
                    Library("Movies", "movie", movies),
                    Library("TV", "series", tv),
                ]
            )

        by_library = {result.name: result for result in results}
        movie_issues = {(issue.type, issue.relative_path) for issue in by_library["Movies"].issues}
        tv_issues = {(issue.type, issue.relative_path) for issue in by_library["TV"].issues}
        all_paths = [issue.relative_path for result in results for issue in result.issues]

        self.assertIn(("empty_directory", "Empty"), movie_issues)
        self.assertIn(("directory_without_video", "Images Only"), movie_issues)
        self.assertIn(("orphaned_sidecar", "Orphans/lost.srt"), movie_issues)
        self.assertIn(("invalid_movie_layout", "Loose.Movie.2024.mkv"), movie_issues)
        self.assertIn(("invalid_movie_layout", "Bad Movie/Bad Movie.mkv"), movie_issues)
        self.assertIn(("small_video_file", "Bad Movie/Bad Movie.mkv"), movie_issues)
        self.assertIn(("invalid_series_layout", "Root.Show.S01E01.mkv"), tv_issues)
        self.assertIn(("invalid_series_layout", "Pantheon (2022)/Pantheon - S01E03.mkv"), tv_issues)
        self.assertIn(("invalid_series_layout", "Good Show (2024)/Season One/Good Show - S01E01.mkv"), tv_issues)
        self.assertIn(("invalid_series_layout", "Another Show (2024)/Season 01/Another Show - Episode 01.mkv"), tv_issues)
        self.assertNotIn("沙丘 Dune (2021)/沙丘 Dune (2021).mkv", [path for issue_type, path in movie_issues if issue_type != "small_video_file"])
        self.assertFalse(any(".@__thumb" in path for path in all_paths))
        self.assertNotIn(str(root), str(by_library["Movies"].to_dict()))

    def test_audit_libraries_reports_read_error_without_stopping(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            movies = root / "movies"
            movie = movies / "沙丘 Dune (2021)" / "沙丘 Dune (2021).mkv"
            movie.parent.mkdir(parents=True)
            movie.write_bytes(b"x")

            with patch("media_manager.media._file_size", side_effect=OSError("permission denied")):
                result = audit_libraries([Library("Movies", "movie", movies)])[0]

        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].type, "read_error")
        self.assertEqual(result.issues[0].relative_path, "沙丘 Dune (2021)/沙丘 Dune (2021).mkv")
        self.assertEqual(result.issues[0].detail, "permission denied")


if __name__ == "__main__":
    unittest.main()

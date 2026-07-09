from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from media_manager.media import MediaItem
from media_manager.rename import apply_rename, preview_rename


class RenameTest(unittest.TestCase):
    def test_preview_reports_conflict(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Movies" / "Old.mkv"
            target = root / "Movies" / "Dune (2021)" / "Dune (2021).mkv"
            source.parent.mkdir()
            target.parent.mkdir()
            source.write_text("", encoding="utf-8")
            target.write_text("", encoding="utf-8")
            item = MediaItem("movie", "Dune", str(source), "Movies", str(root / "Movies"), year=2021)

            preview = preview_rename(item)

        self.assertFalse(preview["can_apply"])
        self.assertIn("target_exists", preview["conflicts"])

    def test_apply_moves_video_sidecars_and_movie_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Movies" / "Old Name" / "old.name.mkv"
            subtitle = video.with_suffix(".chs.ass")
            nfo = video.with_suffix(".nfo")
            movie_nfo = video.parent / "movie.nfo"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            subtitle.write_text("", encoding="utf-8")
            nfo.write_text("<movie />", encoding="utf-8")
            movie_nfo.write_text("<movie />", encoding="utf-8")
            item = MediaItem("movie", "Dune", str(video), "Movies", str(root / "Movies"), year=2021)

            result = apply_rename(item)
            changed = {Path(change["to"]).name for change in result["changes"]}
            renamed_video_exists = (root / "Movies" / "Dune (2021)" / "Dune (2021).mkv").exists()
            renamed_movie_nfo_exists = (root / "Movies" / "Dune (2021)" / "movie.nfo").exists()

        self.assertIn("Dune (2021).mkv", changed)
        self.assertIn("Dune (2021).chs.ass", changed)
        self.assertIn("Dune (2021).nfo", changed)
        self.assertIn("movie.nfo", changed)
        self.assertTrue(renamed_video_exists)
        self.assertTrue(renamed_movie_nfo_exists)

    def test_preview_uses_movie_nfo_bilingual_name_and_preserves_extension(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Movies" / "Old Name" / "old.name.mp4"
            movie_nfo = video.parent / "movie.nfo"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            movie_nfo.write_text(
                """
<movie>
  <title>沙丘</title>
  <originaltitle>Dune</originaltitle>
  <year>2021</year>
</movie>
""".strip(),
                encoding="utf-8",
            )
            item = MediaItem("movie", "Old Name", str(video), "Movies", str(root / "Movies"))

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "Movies" / "Dune - 沙丘 (2021)" / "Dune - 沙丘 (2021).mp4", targets)
        self.assertIn(root / "Movies" / "Dune - 沙丘 (2021)" / "movie.nfo", targets)

    def test_preview_uses_tvshow_nfo_bilingual_name_and_keeps_sxxexx(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "TV" / "Pantheon (2022)" / "Season 01" / "Pantheon - S01E03.mkv"
            episode_nfo = video.with_suffix(".nfo")
            tvshow_nfo = root / "TV" / "Pantheon (2022)" / "tvshow.nfo"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            episode_nfo.write_text("<episodedetails />", encoding="utf-8")
            tvshow_nfo.write_text(
                """
<tvshow>
  <title>万神殿</title>
  <originaltitle>Pantheon</originaltitle>
  <year>2022</year>
</tvshow>
""".strip(),
                encoding="utf-8",
            )
            item = MediaItem(
                "series",
                "Pantheon",
                str(video),
                "TV",
                str(root / "TV"),
                year=2022,
                season=1,
                episode=3,
            )

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "TV" / "Pantheon - 万神殿 (2022)" / "Season 01" / "Pantheon - 万神殿 - S01E03.mkv", targets)
        self.assertIn(root / "TV" / "Pantheon - 万神殿 (2022)" / "Season 01" / "Pantheon - 万神殿 - S01E03.nfo", targets)

    def test_preview_does_not_duplicate_same_local_and_original_title(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Movies" / "Old" / "old.mkv"
            movie_nfo = video.parent / "movie.nfo"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            movie_nfo.write_text(
                """
<movie>
  <title>Dune</title>
  <originaltitle>Dune</originaltitle>
  <year>2021</year>
</movie>
""".strip(),
                encoding="utf-8",
            )
            item = MediaItem("movie", "Old", str(video), "Movies", str(root / "Movies"))

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "Movies" / "Dune (2021)" / "Dune (2021).mkv", targets)

    def test_preview_falls_back_to_scanned_title_without_nfo(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Movies" / "Old" / "old.ts"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            item = MediaItem("movie", "Dune", str(video), "Movies", str(root / "Movies"), year=2021)

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "Movies" / "Dune (2021)" / "Dune (2021).ts", targets)

    def test_preview_falls_back_to_scanned_title_with_partial_nfo(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Movies" / "Old" / "old.mov"
            movie_nfo = video.parent / "movie.nfo"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            movie_nfo.write_text(
                """
<movie>
  <title>沙丘</title>
  <year>2021</year>
</movie>
""".strip(),
                encoding="utf-8",
            )
            item = MediaItem("movie", "Dune", str(video), "Movies", str(root / "Movies"))

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "Movies" / "Dune (2021)" / "Dune (2021).mov", targets)
        self.assertNotIn(root / "Movies" / "沙丘 (2021)" / "沙丘 (2021).mov", targets)

    def test_preview_falls_back_to_scanned_title_with_invalid_nfo(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Movies" / "Old" / "old.avi"
            movie_nfo = video.parent / "movie.nfo"
            video.parent.mkdir(parents=True)
            video.write_text("", encoding="utf-8")
            movie_nfo.write_text("<movie>", encoding="utf-8")
            item = MediaItem("movie", "Dune", str(video), "Movies", str(root / "Movies"), year=2021)

            preview = preview_rename(item)
            targets = {Path(change["to"]) for change in preview["changes"]}

        self.assertIn(root / "Movies" / "Dune (2021)" / "Dune (2021).avi", targets)


if __name__ == "__main__":
    unittest.main()

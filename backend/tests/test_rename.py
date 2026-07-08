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


if __name__ == "__main__":
    unittest.main()

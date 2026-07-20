from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from media_manager.media import MediaItem
from media_manager.nfo import write_nfo


class NfoTest(unittest.TestCase):
    def test_writes_movie_nfo(self) -> None:
        with TemporaryDirectory() as tmp:
            movie = Path(tmp) / "Dune (2021)" / "Dune (2021).mkv"
            movie.parent.mkdir()
            movie.write_text("", encoding="utf-8")
            item = MediaItem("movie", "Dune", str(movie), "Movies", str(Path(tmp)), year=2020)

            nfo_path = write_nfo(
                item,
                {
                    "id": 438631,
                    "title": "Dune",
                    "original_title": "Dune",
                    "english_title": "Dune",
                    "overview": "A noble family becomes embroiled in a war.",
                    "release_date": "2021-09-15",
                },
            )

            root = ET.parse(nfo_path).getroot()
        self.assertEqual(nfo_path.name, "movie.nfo")
        self.assertEqual(root.tag, "movie")
        self.assertEqual(root.findtext("title"), "Dune")
        self.assertEqual(root.findtext("englishtitle"), "Dune")
        self.assertEqual(root.findtext("year"), "2021")
        self.assertEqual(root.findtext("tmdbid"), "438631")

    def test_writes_series_and_episode_nfo(self) -> None:
        with TemporaryDirectory() as tmp:
            episode = Path(tmp) / "Pantheon" / "Season 01" / "Pantheon - S01E03.mkv"
            episode.parent.mkdir(parents=True)
            episode.write_text("", encoding="utf-8")
            item = MediaItem("series", "Pantheon", str(episode), "TV", str(Path(tmp)), season=1, episode=3)

            episode_nfo = write_nfo(item, {"id": 195339, "name": "Pantheon", "overview": "Uploaded intelligence."})
            show_nfo = episode.parents[1] / "tvshow.nfo"

            show_root = ET.parse(show_nfo).getroot()
            episode_root = ET.parse(episode_nfo).getroot()
        self.assertEqual(show_root.tag, "tvshow")
        self.assertEqual(show_root.findtext("tmdbid"), "195339")
        self.assertEqual(episode_root.tag, "episodedetails")
        self.assertEqual(episode_root.findtext("season"), "1")
        self.assertEqual(episode_root.findtext("episode"), "3")


if __name__ == "__main__":
    unittest.main()

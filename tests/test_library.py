"""
Tests for tonal.core.library — pure functions and SQLite operations.

All tests are headless (use QCoreApplication, no display needed).
The Library is initialised with a temporary in-memory / temp-file DB
so nothing touches the real ~/.tonal/library.db.
"""
import sqlite3
import tempfile
import os
import pytest

from tonal.core.library import format_duration, format_ms, Library, SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_zero(self):
        assert format_duration(0) == "0:00"

    def test_negative(self):
        assert format_duration(-5) == "0:00"

    def test_seconds_only(self):
        assert format_duration(45) == "0:45"

    def test_one_minute(self):
        assert format_duration(60) == "1:00"

    def test_minutes_and_seconds(self):
        assert format_duration(3 * 60 + 7) == "3:07"

    def test_one_hour(self):
        assert format_duration(3600) == "1:00:00"

    def test_hours_minutes_seconds(self):
        assert format_duration(2 * 3600 + 34 * 60 + 56) == "2:34:56"

    def test_leading_zero_seconds(self):
        assert format_duration(5 * 60 + 3) == "5:03"


# ---------------------------------------------------------------------------
# format_ms
# ---------------------------------------------------------------------------

class TestFormatMs:
    def test_zero(self):
        assert format_ms(0) == "0:00"

    def test_one_minute_in_ms(self):
        assert format_ms(60_000) == "1:00"

    def test_fractional_seconds_truncated(self):
        # 90_500 ms → 90 s → 1:30
        assert format_ms(90_500) == "1:30"


# ---------------------------------------------------------------------------
# SUPPORTED_EXTENSIONS
# ---------------------------------------------------------------------------

class TestSupportedExtensions:
    def test_mp3_included(self):
        assert ".mp3" in SUPPORTED_EXTENSIONS

    def test_flac_included(self):
        assert ".flac" in SUPPORTED_EXTENSIONS

    def test_m4a_included(self):
        assert ".m4a" in SUPPORTED_EXTENSIONS

    def test_txt_excluded(self):
        assert ".txt" not in SUPPORTED_EXTENSIONS

    def test_all_lowercase(self):
        for ext in SUPPORTED_EXTENSIONS:
            assert ext == ext.lower(), f"Extension {ext!r} is not lowercase"


# ---------------------------------------------------------------------------
# Library — SQLite operations
# (uses a temporary file so the real DB is never touched)
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_library(qapp, tmp_path):
    """A fresh Library backed by a temp file DB."""
    db = str(tmp_path / "test.db")
    lib = Library(db)
    yield lib


class TestLibraryEmpty:
    """Queries against an empty library must return sensible defaults."""

    def test_get_all_tracks_empty(self, tmp_library):
        assert tmp_library.get_all_tracks() == []

    def test_get_artists_empty(self, tmp_library):
        assert tmp_library.get_artists() == []

    def test_get_albums_empty(self, tmp_library):
        assert tmp_library.get_albums() == []

    def test_get_folders_empty(self, tmp_library):
        assert tmp_library.get_folders() == []

    def test_track_count_empty(self, tmp_library):
        assert tmp_library.track_count() == 0

    def test_search_empty(self, tmp_library):
        assert tmp_library.search("anything") == []


def _insert_track(db_path, **kwargs):
    """Helper: insert a track row directly via sqlite3."""
    defaults = dict(
        path="/music/test.mp3",
        title="Test Track",
        artist="Test Artist",
        album="Test Album",
        album_artist="Test Artist",
        year=2024,
        track_number=1,
        disc_number=1,
        duration=180,
        genre="Rock",
        has_cover=0,
    )
    defaults.update(kwargs)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO tracks
           (path, title, artist, album, album_artist, year,
            track_number, disc_number, duration, genre, has_cover)
           VALUES
           (:path, :title, :artist, :album, :album_artist, :year,
            :track_number, :disc_number, :duration, :genre, :has_cover)""",
        defaults,
    )
    conn.commit()
    conn.close()


class TestLibraryWithData:
    """Queries after inserting tracks directly into the DB."""

    def test_get_all_tracks_returns_row(self, tmp_library):
        _insert_track(tmp_library._db_path)
        tracks = tmp_library.get_all_tracks()
        assert len(tracks) == 1
        assert tracks[0]["title"] == "Test Track"

    def test_track_count_increments(self, tmp_library):
        _insert_track(tmp_library._db_path, path="/music/a.mp3")
        _insert_track(tmp_library._db_path, path="/music/b.mp3")
        assert tmp_library.track_count() == 2

    def test_get_artists_returns_distinct(self, tmp_library):
        _insert_track(tmp_library._db_path, path="/music/a.mp3", artist="Alpha")
        _insert_track(tmp_library._db_path, path="/music/b.mp3", artist="Alpha")
        _insert_track(tmp_library._db_path, path="/music/c.mp3", artist="Beta")
        artists = tmp_library.get_artists()
        assert artists == ["Alpha", "Beta"]

    def test_get_albums_returns_distinct(self, tmp_library):
        _insert_track(tmp_library._db_path, path="/music/a.mp3", album="Album A")
        _insert_track(tmp_library._db_path, path="/music/b.mp3", album="Album B")
        albums = tmp_library.get_albums()
        assert set(albums) == {"Album A", "Album B"}

    def test_get_tracks_by_artist(self, tmp_library):
        _insert_track(tmp_library._db_path, path="/music/a.mp3", artist="Solo")
        _insert_track(tmp_library._db_path, path="/music/b.mp3", artist="Other")
        result = tmp_library.get_tracks_by_artist("Solo")
        assert len(result) == 1
        assert result[0]["artist"] == "Solo"

    def test_get_tracks_by_album(self, tmp_library):
        _insert_track(tmp_library._db_path, path="/music/a.mp3", album="My Album")
        _insert_track(tmp_library._db_path, path="/music/b.mp3", album="Other Album")
        result = tmp_library.get_tracks_by_album("My Album")
        assert len(result) == 1
        assert result[0]["album"] == "My Album"

    def test_search_by_title(self, tmp_library):
        _insert_track(tmp_library._db_path, path="/music/a.mp3", title="Moonlight Sonata")
        _insert_track(tmp_library._db_path, path="/music/b.mp3", title="River Flows")
        assert len(tmp_library.search("Moonlight")) == 1
        assert len(tmp_library.search("Flows")) == 1

    def test_search_by_artist(self, tmp_library):
        _insert_track(tmp_library._db_path, path="/music/a.mp3", artist="Beethoven")
        assert len(tmp_library.search("beet")) == 1  # case-insensitive LIKE

    def test_search_no_match(self, tmp_library):
        _insert_track(tmp_library._db_path)
        assert tmp_library.search("zzznomatch") == []

    def test_delete_track(self, tmp_library):
        _insert_track(tmp_library._db_path, path="/music/delete_me.mp3")
        assert tmp_library.track_count() == 1
        tmp_library.delete_track("/music/delete_me.mp3")
        assert tmp_library.track_count() == 0

    def test_remove_folder(self, tmp_library, tmp_path):
        folder = str(tmp_path / "Music")
        os.makedirs(folder)
        # Insert a track under that folder and register the folder
        track_path = os.path.join(folder, "song.mp3")
        _insert_track(tmp_library._db_path, path=track_path)
        conn = sqlite3.connect(tmp_library._db_path)
        conn.execute("INSERT OR IGNORE INTO folders (path) VALUES (?)", (folder,))
        conn.commit()
        conn.close()

        assert tmp_library.track_count() == 1
        assert folder in tmp_library.get_folders()

        tmp_library.remove_folder(folder)

        assert tmp_library.track_count() == 0
        assert folder not in tmp_library.get_folders()

    def test_track_dict_has_expected_keys(self, tmp_library):
        _insert_track(tmp_library._db_path)
        track = tmp_library.get_all_tracks()[0]
        for key in ("path", "title", "artist", "album", "duration"):
            assert key in track, f"Missing key: {key}"

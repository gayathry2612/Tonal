"""
Music library: file scanning, metadata extraction, and SQLite persistence.

Scanning runs in a QThread so the UI stays responsive.  Progress is
reported via Qt signals.
"""
from __future__ import annotations   # allows X | Y union hints on Python 3.9

import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3
    from mutagen.mp4 import MP4
    from mutagen.flac import FLAC
    _MUTAGEN_OK = True
except ImportError:
    _MUTAGEN_OK = False

try:
    from PIL import Image
    import io as _io
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


SUPPORTED_EXTENSIONS = {
    ".mp3", ".flac", ".wav", ".ogg", ".m4a",
    ".aac", ".wma", ".opus", ".ape", ".aiff",
}

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS tracks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT    UNIQUE NOT NULL,
    title        TEXT,
    artist       TEXT,
    album        TEXT,
    album_artist TEXT,
    year         INTEGER,
    track_number INTEGER,
    disc_number  INTEGER,
    duration     INTEGER,
    genre        TEXT,
    has_cover    INTEGER DEFAULT 0,
    date_added   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS folders (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS playlists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE,
    track_id    INTEGER REFERENCES tracks(id)    ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, position)
);
"""


# ---------------------------------------------------------------------------
# Background scanner thread
# ---------------------------------------------------------------------------

class _ScanWorker(QObject):
    """Runs inside a QThread; scans a folder and inserts tracks into the DB."""

    progress = Signal(str, int)   # (current_file_path, tracks_found_so_far)
    finished = Signal(int)        # total tracks added
    error    = Signal(str)

    def __init__(self, folder: str, db_path: str):
        super().__init__()
        self._folder  = folder
        self._db_path = db_path

    @Slot()
    def run(self) -> None:
        try:
            added = self._scan()
            self.finished.emit(added)
        except Exception as exc:
            self.error.emit(str(exc))

    def _scan(self) -> int:
        added = 0
        conn  = sqlite3.connect(self._db_path)
        try:
            conn.executescript(_SCHEMA)
            for root, _dirs, files in os.walk(self._folder):
                for fname in files:
                    if Path(fname).suffix.lower() not in SUPPORTED_EXTENSIONS:
                        continue
                    full = os.path.join(root, fname)
                    meta = _extract_metadata(full)
                    if meta is None:
                        continue
                    try:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO tracks
                              (path, title, artist, album, album_artist,
                               year, track_number, disc_number, duration, genre, has_cover)
                            VALUES
                              (:path, :title, :artist, :album, :album_artist,
                               :year, :track_number, :disc_number, :duration, :genre, :has_cover)
                            """,
                            meta,
                        )
                        added += 1
                        self.progress.emit(full, added)
                    except sqlite3.Error:
                        pass
            conn.execute(
                "INSERT OR IGNORE INTO folders (path) VALUES (?)", (self._folder,)
            )
            conn.commit()
        finally:
            conn.close()
        return added


# ---------------------------------------------------------------------------
# Metadata extraction (mutagen)
# ---------------------------------------------------------------------------

def _tag(audio, *keys) -> str | None:
    """Try multiple tag key names; return first non-empty string found."""
    for key in keys:
        val = audio.get(key)
        if val:
            item = val[0] if isinstance(val, list) else val
            s = str(item).strip()
            if s:
                return s
    return None


def _int_tag(audio, *keys) -> int | None:
    raw = _tag(audio, *keys)
    if raw is None:
        return None
    try:
        return int(raw.split("/")[0])
    except (ValueError, AttributeError):
        return None


def _extract_metadata(path: str) -> dict | None:
    """Return a dict ready for DB insertion, or None on failure."""
    p = Path(path)
    if not _MUTAGEN_OK:
        return {
            "path": path, "title": p.stem, "artist": "Unknown Artist",
            "album": "Unknown Album", "album_artist": None, "year": None,
            "track_number": None, "disc_number": None, "duration": 0,
            "genre": None, "has_cover": 0,
        }
    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            return None

        duration = int(audio.info.length) if hasattr(audio, "info") else 0
        title    = _tag(audio, "title") or p.stem
        artist   = _tag(audio, "artist") or "Unknown Artist"
        album    = _tag(audio, "album")  or "Unknown Album"
        album_artist = (
            _tag(audio, "albumartist", "album artist") or artist
        )
        year         = _int_tag(audio, "date", "year")
        track_number = _int_tag(audio, "tracknumber")
        disc_number  = _int_tag(audio, "discnumber")
        genre        = _tag(audio, "genre")

        has_cover = int(_has_embedded_art(path))

        return {
            "path": path, "title": title, "artist": artist, "album": album,
            "album_artist": album_artist, "year": year,
            "track_number": track_number, "disc_number": disc_number,
            "duration": duration, "genre": genre, "has_cover": has_cover,
        }
    except Exception:
        return None


def _has_embedded_art(path: str) -> bool:
    """Return True if the file has embedded album art."""
    if not _MUTAGEN_OK:
        return False
    try:
        ext = Path(path).suffix.lower()
        if ext == ".mp3":
            tags = ID3(path)
            return any(k.startswith("APIC") for k in tags.keys())
        elif ext == ".flac":
            f = FLAC(path)
            return bool(f.pictures)
        elif ext in (".m4a", ".aac", ".mp4"):
            f = MP4(path)
            return "covr" in f
    except Exception:
        pass
    return False


def get_album_art_bytes(path: str) -> bytes | None:
    """Extract raw album art bytes from an audio file."""
    if not _MUTAGEN_OK:
        return None
    try:
        ext = Path(path).suffix.lower()
        if ext == ".mp3":
            tags = ID3(path)
            for key in tags.keys():
                if key.startswith("APIC"):
                    return tags[key].data
        elif ext == ".flac":
            f = FLAC(path)
            if f.pictures:
                return f.pictures[0].data
        elif ext in (".m4a", ".aac", ".mp4"):
            f = MP4(path)
            if "covr" in f:
                return bytes(f["covr"][0])
        else:
            # Generic: try mutagen non-easy
            audio = MutagenFile(path)
            if audio and hasattr(audio, "pictures") and audio.pictures:
                return audio.pictures[0].data
    except Exception:
        pass
    return None


def format_duration(seconds: int) -> str:
    """Convert integer seconds → 'M:SS' or 'H:MM:SS'."""
    if seconds < 0:
        return "0:00"
    h, rem = divmod(int(seconds), 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_ms(ms: int) -> str:
    """Convert milliseconds → 'M:SS'."""
    return format_duration(ms // 1000)


# ---------------------------------------------------------------------------
# Library class
# ---------------------------------------------------------------------------

class Library(QObject):
    """
    Manages the on-disk SQLite library and provides query methods.

    Scanning is offloaded to a QThread.  Connect to scan_progress and
    scan_finished to update the UI.
    """

    scan_progress = Signal(str, int)  # (file_path, count_so_far)
    scan_finished = Signal(int)       # total tracks added
    scan_error    = Signal(str)

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._thread: QThread | None = None
        self._worker: _ScanWorker | None = None
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.executescript(_SCHEMA)
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def scan_folder(self, folder: str) -> None:
        """Start an async folder scan.  Only one scan runs at a time."""
        if self._thread and self._thread.isRunning():
            return

        self._thread = QThread(self)
        self._worker = _ScanWorker(folder, self._db_path)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.scan_progress)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self.scan_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    @Slot(int)
    def _on_scan_finished(self, count: int) -> None:
        self.scan_finished.emit(count)

    def remove_folder(self, folder: str) -> None:
        """Remove a watched folder and all tracks under it from the library."""
        with self._conn() as conn:
            conn.execute("DELETE FROM tracks WHERE path LIKE ?", (folder + "%",))
            conn.execute("DELETE FROM folders WHERE path = ?", (folder,))
            conn.commit()

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_all_tracks(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tracks ORDER BY artist, album, track_number, title"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_artists(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT artist FROM tracks ORDER BY artist"
            ).fetchall()
        return [r[0] for r in rows]

    def get_albums(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT album FROM tracks ORDER BY album"
            ).fetchall()
        return [r[0] for r in rows]

    def get_tracks_by_artist(self, artist: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tracks WHERE artist = ? ORDER BY album, track_number, title",
                (artist,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_tracks_by_album(self, album: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tracks WHERE album = ? ORDER BY track_number, title",
                (album,),
            ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str) -> list[dict]:
        q = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tracks
                WHERE  title LIKE ? OR artist LIKE ? OR album LIKE ?
                ORDER  BY artist, album, title
                """,
                (q, q, q),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_folders(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT path FROM folders ORDER BY path").fetchall()
        return [r[0] for r in rows]

    def track_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]

    def delete_track(self, path: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM tracks WHERE path = ?", (path,))
            conn.commit()

# Tonal — Portable Music Player
## Design Document v1.0

---

## 1. Overview

**Tonal** is a free, cross-platform, locally-installed desktop music player built with Python. It requires no internet connection, no online accounts, and no subscriptions. Users point it at their local music folders and it manages the rest.

**Target platforms:** macOS (primary), Windows, Linux
**Language:** Python 3.11+
**License:** MIT

---

## 2. Goals

| Goal | Detail |
|------|--------|
| Free | Zero cost, no ads, no telemetry |
| Portable | No server, no cloud, everything local |
| Installable | One-click installer (.dmg on Mac, .exe on Windows) |
| Cross-platform | macOS, Windows, Linux via Python + Qt |
| Pythonic | Python-first stack, minimal native code |

---

## 3. Technology Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| GUI Framework | **PySide6** (Qt 6) | LGPL-licensed, native look, excellent cross-platform |
| Audio Engine | **PySide6.QtMultimedia** (QMediaPlayer) | Built-in Qt, uses AVFoundation on Mac, no extra install |
| Metadata | **mutagen** | Best Python library for audio tags (MP3, FLAC, M4A, OGG…) |
| Image Processing | **Pillow** | Album art extraction and resizing |
| Database | **SQLite** (stdlib) | Zero-config, file-based, built into Python |
| Packaging | **PyInstaller** | Single-folder or single-file app bundles |
| Mac DMG | **create-dmg** (optional brew) | Wraps .app into distributable .dmg |

---

## 4. Supported Audio Formats

| Format | Extension |
|--------|-----------|
| MP3 | .mp3 |
| FLAC | .flac |
| AAC / M4A | .m4a, .aac |
| OGG Vorbis | .ogg |
| WAV | .wav |
| OPUS | .opus |
| WMA | .wma |

---

## 5. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Tonal Application                        │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                      UI Layer (PySide6)                  │   │
│  │                                                          │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │   │
│  │  │ LibraryPanel│  │  TrackList   │  │ PlayerControls │  │   │
│  │  │  (sidebar)  │  │  (QTable)    │  │  (bottom bar)  │  │   │
│  │  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │   │
│  │         │                │                   │           │   │
│  │  ┌──────┴────────────────┴───────────────────┴────────┐  │   │
│  │  │                   MainWindow                       │  │   │
│  │  └──────────────────────────┬─────────────────────────┘  │   │
│  └─────────────────────────────┼────────────────────────────┘   │
│                                │ signals / slots                 │
│  ┌─────────────────────────────┼────────────────────────────┐   │
│  │                    Core Layer│                            │   │
│  │                             │                            │   │
│  │  ┌──────────────┐  ┌────────┴────────┐                   │   │
│  │  │    Library   │  │     Player      │                   │   │
│  │  │  (SQLite DB) │  │  (QMediaPlayer) │                   │   │
│  │  └──────┬───────┘  └─────────────────┘                   │   │
│  │         │                                                 │   │
│  │  ┌──────┴───────┐                                        │   │
│  │  │   Scanner    │  (mutagen + Pillow)                    │   │
│  │  └──────────────┘                                        │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │              Storage Layer                                 │   │
│  │   ~/.tonal/library.db   (SQLite)                          │   │
│  │   ~/.tonal/settings.ini (QSettings)                       │   │
│  └────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Data Model

### `tracks` table
```sql
CREATE TABLE tracks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    path          TEXT    UNIQUE NOT NULL,
    title         TEXT,
    artist        TEXT,
    album         TEXT,
    album_artist  TEXT,
    year          INTEGER,
    track_number  INTEGER,
    disc_number   INTEGER,
    duration      INTEGER,   -- seconds
    genre         TEXT,
    has_cover     INTEGER DEFAULT 0,
    date_added    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `folders` table
```sql
CREATE TABLE folders (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    path  TEXT UNIQUE NOT NULL
);
```

### `playlists` / `playlist_tracks` tables
```sql
CREATE TABLE playlists (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE playlist_tracks (
    playlist_id INTEGER REFERENCES playlists(id),
    track_id    INTEGER REFERENCES tracks(id),
    position    INTEGER,
    PRIMARY KEY (playlist_id, track_id)
);
```

---

## 7. UI Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  🎵 Tonal                               [  Search...  ]   _ □ × │
├──────────────┬───────────────────────────────────────────────────┤
│              │  Artist / Album / Song             Dur    Added   │
│  LIBRARY     │ ─────────────────────────────────────────────     │
│  ──────────  │  ▶ Bohemian Rhapsody      Queen    5:55          │
│  ♫ Songs     │    Hotel California       Eagles   6:30          │
│  👤 Artists  │    Stairway to Heaven     Led Zep  8:02          │
│  💿 Albums   │    Comfortably Numb       Pink F.  6:21          │
│              │    Wish You Were Here     Pink F.  5:34          │
│  FOLDERS     │    ...                                            │
│  ──────────  │                                                   │
│  ~/Music     │                                                   │
│  + Add       │                                                   │
│              │                                                   │
├──────────────┴───────────────────────────────────────────────────┤
│  ┌────────┐  Bohemian Rhapsody                    ⏮  ⏪  ⏯  ⏩  ⏭ │
│  │ [Art]  │  Queen • A Night at the Opera         🔀  🔁         │
│  └────────┘  ──────────────○─────────────  2:13 / 5:55  🔊────  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. Component Descriptions

### `MainWindow`
- Central coordinator: owns `Library`, `Player`, and all UI panels
- Handles signals/slots wiring between components
- Persists window geometry and last state via `QSettings`

### `LibraryPanel` (left sidebar)
- Navigation list: Songs, Artists, Albums
- Watched folders list with Add/Remove buttons
- Emits `view_changed(mode)` signal when user switches sections

### `TrackListView` (centre)
- `QTableWidget` with sortable columns: Track #, Title, Artist, Album, Duration
- Alternating row colours, current track highlighted in accent colour
- Double-click → play track; right-click → context menu (Play, Queue, Info)
- Header search filter

### `PlayerControls` (bottom bar)
- Album art thumbnail (60×60 px)
- Track title + artist labels (truncated with ellipsis)
- Seek slider with elapsed / total time
- Transport buttons: ⏮ Prev, ⏪ Rewind 10s, ⏯ Play/Pause, ⏩ Forward 10s, ⏭ Next
- Shuffle toggle, Repeat toggle (None → All → One)
- Volume slider

### `Player` (core)
- Wraps `QMediaPlayer` + `QAudioOutput`
- Manages track queue with shuffle/repeat logic
- Emits Qt signals consumed by UI
- Handles end-of-media auto-advance

### `Library` (core)
- Owns the SQLite connection
- `scan_folder()` runs in a `QThread` to avoid UI freeze
- Provides query methods: `get_all_tracks()`, `get_by_artist()`, etc.

---

## 9. Player State Machine

```
          load_queue()
STOPPED ──────────────► LOADING
                           │
                        play()
                           ▼
                        PLAYING ◄────────────────┐
                           │                     │
                       pause()              unpause()
                           │                     │
                           ▼                     │
                        PAUSED ──────────────────┘
                           │
                       stop() / end of queue
                           ▼
                        STOPPED
```

---

## 10. File / Folder Layout

```
music-player/
├── src/
│   └── tonal/
│       ├── __init__.py
│       ├── main.py                 # entry point
│       ├── core/
│       │   ├── __init__.py
│       │   ├── player.py           # QMediaPlayer wrapper
│       │   └── library.py          # SQLite + mutagen scanner
│       └── ui/
│           ├── __init__.py
│           ├── main_window.py      # QMainWindow
│           ├── player_controls.py  # bottom player bar
│           ├── library_panel.py    # left sidebar
│           ├── track_list.py       # centre track table
│           └── theme.py            # QSS dark stylesheet
├── assets/
│   └── icons/                      # (bundled SVG icons)
├── docs/
│   └── design.md                   # this file
├── installer/
│   ├── tonal.spec                  # PyInstaller spec
│   └── build_mac.sh                # Mac build + dmg script
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 11. Build & Install

### Development
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m tonal
```

### macOS distributable
```bash
bash installer/build_mac.sh
# → dist/Tonal.dmg
```

### Windows distributable
```bash
pyinstaller installer/tonal.spec
# → dist/Tonal/Tonal.exe
```

---

## 12. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PySide6 | ≥6.6 | GUI + audio (Qt Multimedia) |
| mutagen | ≥1.47 | Audio metadata reading |
| Pillow | ≥10.0 | Album art processing |
| PyInstaller | ≥6.0 | Packaging (dev only) |

All runtime deps are bundled into the installer. End users install nothing beyond the .dmg / .exe.

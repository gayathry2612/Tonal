# Tonal

> *Your music. Your machine. No middleman.*

---

## Why does Tonal exist in a world with Spotify?

Spotify is incredible. Thirty million songs in your pocket, curated playlists, collaborative listening — it's genuinely magic.

But it's also a subscription. A dependency. A server farm in another country deciding whether your favourite deep-cut album stays licensed this month. A company that can, and does, remove music without warning. An app that requires an account just to press play.

And then there's *your* music. The stuff that will never be on Spotify. The bootleg recording of a gig you went to in 2009. The lossless FLAC rips you spent years building. The MP3s you bought on Bandcamp from artists who actually get paid when you buy directly. The playlist you made for a person who mattered. Voice memos. Field recordings. Your dad's record collection, digitised.

**That music deserves a great player. That's Tonal.**

No account. No ads. No algorithm nudging you toward sponsored content. No phone home. No internet required — ever. Just a beautiful, fast, native app that plays your files and gets out of the way.

---

## What it does

- **Local library** — point it at a folder, it scans and remembers everything
- **Browse** by Songs, Artists, or Albums
- **Search** across title, artist, and album instantly
- **Playback controls** — play/pause, previous/next, seek, skip ±10 s
- **Shuffle & Repeat** — Off / All / One
- **Album art** extracted from the embedded tags in your files
- **Space animations** — because why not, it's your music player
- **Dark theme**, keyboard-friendly
- **Remembers** your window size and volume between sessions
- **Formats** — MP3, FLAC, M4A/AAC, OGG, WAV, OPUS, WMA, AIFF, APE

---

## Quick start

```bash
git clone <this-repo>
cd "Music player"

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python -m tonal
```

Requires **Python 3.12+**.

---

## Install (no Python needed for end users)

### macOS

```bash
brew install create-dmg          # one-time
bash installer/build_mac.sh
# → dist/Tonal.dmg
```

Drag `Tonal.app` to `/Applications`. Done.

### Windows

```bat
installer\build_windows.bat
REM → dist\Tonal\Tonal.exe
```

### Linux

```bash
source .venv/bin/activate
pyinstaller installer/tonal.spec --noconfirm
# → dist/tonal
```

---

## Custom icon

Have a PNG? Generate the macOS icon in one command:

```bash
python installer/make_icns.py path/to/your_icon.png
# → assets/icons/tonal.icns  (app bundle icon)
# → assets/icons/tonal.png   (runtime window icon)
```

Then rebuild.

---

## Project structure

```
Music player/
├── src/tonal/
│   ├── main.py                     # Entry point
│   ├── core/
│   │   ├── player.py               # Audio engine (QMediaPlayer + AVFoundation)
│   │   └── library.py              # SQLite library + mutagen metadata scanner
│   └── ui/
│       ├── main_window.py          # Coordinator — wires everything together
│       ├── animated_background.py  # Space scene (stars, nebulae, shooting stars)
│       ├── player_controls.py      # Bottom transport bar
│       ├── library_panel.py        # Left sidebar navigation
│       ├── track_list.py           # Centre track table
│       └── theme.py                # Dark QSS stylesheet
├── assets/icons/                   # tonal.icns / tonal.png (add your icon here)
├── tests/                          # 41 pytest tests, fully headless
├── installer/
│   ├── tonal.spec                  # PyInstaller spec
│   ├── make_icns.py                # PNG → .icns converter
│   ├── build_mac.sh                # macOS build → .dmg
│   └── build_windows.bat           # Windows build → .exe
├── docs/design.md                  # Architecture & design document
├── requirements.txt
└── pyproject.toml
```

---

## Tech stack

| | |
|---|---|
| **Language** | Python 3.12 |
| **GUI** | PySide6 (Qt 6) |
| **Audio** | QMediaPlayer → AVFoundation (Mac) / DirectShow (Windows) |
| **Metadata** | mutagen |
| **Database** | SQLite (stdlib — zero config, zero dependencies) |
| **Packaging** | PyInstaller + create-dmg |
| **Tests** | pytest — 41 tests, no display required |
| **CI** | GitHub Actions |

---

## A note on how this was built

Tonal is a pure product of **vibe coding with Claude**.

No boilerplate was copy-pasted from Stack Overflow. No tutorials were followed. The entire codebase — architecture, Qt signal wiring, audio engine, space animations, installer spec, test suite, CI pipeline — was grown in conversation, one idea at a time, between a person who knew what they wanted and an AI that knew how to build it.

That's the whole point. You don't need to know PySide6. You don't need to know PyInstaller. You don't need to have written a music player before. You just need a clear idea of what you want to exist in the world, and the willingness to iterate.

**Tonal is proof that the barrier to building real, native, polished desktop software is now just: having something worth building.**

---

## License

MIT — free to use, modify, and distribute.

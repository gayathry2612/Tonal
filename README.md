# Tonal

> *Your music. Your machine. No middleman.*
Adiye Thunai - Yadyat Karma Karomi Tattadakhilam Sambho Tavaaradhanam 
---

## Why does Tonal exist in a world with Spotify?

Spotify is incredible!
Thirty million songs in your pocket, curated playlists, collaborative listening — it's genuinely magic.

But it's also a subscription. A dependency on internet. 
A server farm in another country deciding whether your favourite deep-cut album stays licensed this month. 
A company that can, and does, remove music without warning. An app that requires an account just to press play.

And then there's *your* music. The stuff that may never be on Spotify. 
The bootleg recording of a gig you went to in 2009. The lossless FLAC rips you spent years building. 
The MP3s you bought on Bandcamp from artists who actually get paid when you buy directly. 
The playlist you made for a person who mattered. Voice memos. Field recordings. 
Your dad's record collection, digitised that stays on a USB stick. 

**That music deserves a humble music player. That's Tonal.**

No account. No ads. No algorithm nudging you toward sponsored content.
No phone home. No internet required — ever.
Just a beautiful, fast, customisable, native python app that plays your files and gets out of the way.
If you wish to customise this, just fork this repo and play with your favorite AI to add features.

Now with optional Spotify Premium and YouTube Music integration when you want the best of both worlds.

---

## What it does

### Local Music
- **Local library** — point it at a folder, it scans and remembers everything
- **Browse** by Songs, Artists, or Albums
- **Search** across title, artist, and album instantly
- **Playback controls** — play/pause, previous/next, seek, skip ±10 s
- **Shuffle & Repeat** — Off / All / One
- **Album art** extracted from embedded tags
- **Formats** — MP3, FLAC, M4A/AAC, OGG, WAV, OPUS, WMA, AIFF, APE

### Spotify Integration *(optional — requires `spotipy` + Spotify Premium)*
- **OAuth 2.0** — authenticate with your Spotify Developer app credentials (Client ID + Client Secret)
- **Search** Spotify's full catalogue from inside Tonal; results are scoped to your account's country automatically
- **Spotify Connect playback** — double-click any result to play it on your active Spotify device (desktop app, web player, phone)
- **Device picker** — if no device is active, Tonal lists all available devices so you can choose; or opens the Spotify web player directly when nothing is registered
- **Persistent session** — tokens are cached and auto-refreshed; scope changes trigger a one-time re-auth automatically
- **Configurable redirect URI** — set the exact URI you registered in your Spotify app dashboard (`https://localhost/callback` by default)
- **Paste-back auth flow** — works without any local HTTP server; after authorising in the browser just paste the redirect URL back into Tonal

### YouTube Music Integration *(optional — requires `ytmusicapi` + `yt-dlp`)*
- **Google Sign-In** — sign in with your Google account via Device Authorization Flow (no passwords stored in Tonal)
- **Search** YouTube Music for songs, videos, and albums
- **Direct streaming** — audio is extracted by yt-dlp and played through Tonal's own audio engine, so seek, volume, and transport controls all work natively
- **No browser required** — streams play inside the app, not in a separate window
- **Unauthenticated search** — basic searching works without signing in; sign-in unlocks personalised results

### Alarm Clock
- **Schedule any track** as a wake-up alarm — choose from your local library, Spotify, or YouTube Music
- **Flexible repeat** — one-time, daily, weekdays, weekends, or any custom day combination
- **⏰ toolbar button** — open the alarm manager at any time to add, edit, enable/disable, or delete alarms
- **Smart trigger** — a background timer checks every 30 seconds; one-time alarms auto-disable after firing
- **Background mode** — when you close the window with active alarms, Tonal minimises to the system tray and keeps running; alarms fire even while the window is hidden, then automatically bring the app back to the foreground

### App-wide
- **Three-tab layout** — Local Music / Spotify / YouTube Music, tab remembered between sessions
- **System tray** — close the window with active alarms and Tonal keeps running silently in the background; double-click the tray icon to reopen, right-click for the menu, "Quit Tonal" to fully exit
- **Space animations** — because why not, it's your music player
- **Dark theme**, keyboard-friendly
- **Remembers** your window size, splitter position, active tab, and volume between sessions

---

## Quick start

```bash
git clone <this-repo>
cd "Tonal"

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"          # or: pip install -r requirements.txt
python -m tonal
```

Requires **Python 3.12+**.

### Optional streaming dependencies

```bash
# Spotify integration
pip install spotipy requests

# YouTube Music integration
pip install ytmusicapi yt-dlp requests
```

`requests` is shared by both streaming integrations (Spotify direct API calls + YouTube OAuth flow).
Both integrations degrade gracefully — if a package is missing the relevant tab shows an install prompt rather than crashing.

---

## Setting up Spotify

### 1 — Create a Spotify Developer App (free)
1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → **Create app**
2. In **Edit Settings → Redirect URIs** add exactly: `https://localhost/callback` — Spotify now requires HTTPS even for localhost
3. Copy your **Client ID** and **Client Secret** from the dashboard

### 2 — Connect in Tonal
4. Open the **Spotify** tab → enter the Client ID, Client Secret, and `https://localhost/callback` as the Redirect URI
5. Click **Connect to Spotify** — your browser opens the Spotify authorisation page
6. Click **Allow**. Spotify redirects to `https://localhost/callback?code=…`. The browser shows a connection error — **this is normal**; there is no server listening there
7. Copy the full URL from your browser's address bar and paste it into the field that appeared in Tonal → click **Submit**

### 3 — Playing tracks
- Double-click any search result to play it on your active Spotify device
- If no device is active, Tonal shows a **device picker** listing all registered Spotify clients — desktop app, phone, tablet — so you can choose one
- If no devices are registered at all, use **Open Web Player** to launch [open.spotify.com](https://open.spotify.com) in your browser; once it loads it registers as a device and Tonal can target it
- Playback control requires **Spotify Premium**; searching works on any account tier

> **Tip — add yourself as a user in Dev Mode:**
> New Spotify apps are in Development Mode, which limits access to 25 users.
> Go to your app → **User Management** and add your own Spotify account email if you see login errors.

---

## Setting up YouTube Music

1. In Tonal → **YouTube Music tab** → click **Sign in with Google**
2. A short device code appears — use the **Copy code** and **Open URL** buttons
3. On the Google authorisation page, enter the code and grant access
4. Tonal polls automatically; the search panel appears once authorisation is confirmed
5. Searching also works without signing in — sign-in unlocks personalised results and higher-quality streams

---

## Troubleshooting

### macOS — permission prompt on first play
On macOS 13+, AVFoundation requests access to your media files the first time audio plays.
Tonal defers this until you actually press **Play**, so the dialog appears in context rather than at launch.
Grant access once and macOS remembers it for future sessions.

### Spotify — "INVALID_CLIENT: Insecure redirect URI"
Spotify no longer accepts `http://` redirect URIs (even `http://localhost`).
Make sure both the dashboard and the Tonal **Redirect URI** field contain exactly `https://localhost/callback`.
Old configs are migrated automatically when you restart Tonal.

### Spotify — "Insufficient client scope" / search fails after update
If Tonal was updated and the cached token no longer covers all required scopes,
the cache is deleted automatically and the auth page is shown.
Click **Connect to Spotify** to issue a new token with the full scope set.

### Spotify — "No active Spotify device found"
Spotify Connect requires an active Spotify client.
Open the Spotify desktop app, mobile app, or [open.spotify.com](https://open.spotify.com) and play something briefly.
The client registers itself as a device; double-click the track in Tonal to route playback there.
If you see the device picker, select any listed client.

### YouTube Music — "No translation file found for domain: base"
This is a packaging issue in some `ytmusicapi` installs where locale data files are absent.

```bash
pip install --force-reinstall ytmusicapi
```

Then restart Tonal. Tonal also tries `YTMusic(language="en")` automatically to skip the locale lookup in ytmusicapi ≥ 1.7.

### Alarms don't auto-play
On macOS the audio permission dialog can interrupt autoplay before the permission is granted.
Play any local track once to grant permission, then set your alarm — it will fire reliably on subsequent launches.

---

## Install (no Python needed for end users)

### macOS

```bash
$ brew install create-dmg          # one-time
$ bash installer/build_mac.sh
# → dist/Tonal.dmg
```
If there is a problem to access requirements.txt, head to the installer folder and execute build_mac.sh
$ chmod +x build_mac.sh
$ zsh build_mac.sh 

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
Tonal/
├── src/tonal/
│   ├── main.py                     # Entry point
│   ├── core/
│   │   ├── player.py               # Audio engine (QMediaPlayer + AVFoundation)
│   │   ├── library.py              # SQLite library + mutagen metadata scanner
│   │   └── alarm_manager.py        # Alarm CRUD + 30s timer trigger
│   └── ui/
│       ├── main_window.py          # Coordinator — wires everything together
│       ├── animated_background.py  # Space scene (stars, nebulae, shooting stars)
│       ├── player_controls.py      # Bottom transport bar
│       ├── library_panel.py        # Left sidebar navigation
│       ├── track_list.py           # Centre track table
│       ├── spotify_panel.py        # Spotify OAuth + search + Connect playback
│       ├── youtube_panel.py        # YTMusic search + yt-dlp streaming
│       ├── alarm_dialog.py         # Alarm manager dialog + 3-source song picker
│       └── theme.py                # Dark QSS stylesheet
├── assets/icons/                   # tonal.icns / tonal.png (add your icon here)
├── tests/                          # pytest tests, fully headless
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
| **Spotify** | spotipy — OAuth 2.0 (Authorization Code), Web API, Spotify Connect |
| **YouTube Music** | ytmusicapi (search) + yt-dlp (stream extraction) |
| **Packaging** | PyInstaller + create-dmg |
| **Tests** | pytest — headless, no display required |
| **CI** | GitHub Actions |

---

## Data & privacy

All data stays on your machine:

| File | Contents |
|------|----------|
| `~/.tonal/library.db` | Local music metadata (SQLite) |
| `~/.tonal/alarms.json` | Your configured alarms |
| `~/.tonal/spotify_config.json` | Your Spotify Client ID, Client Secret, and Redirect URI |
| `~/.tonal/spotify_cache.json` | Spotify OAuth tokens (never shared) |
| `~/.tonal/youtube_oauth.json` | YouTube Music OAuth tokens (never shared) |

Tonal makes no network requests unless you're actively using the Spotify or YouTube Music tabs.

---

## A note on how this was built

Tonal is a pure product of **vibe coding with Claude**.

No boilerplate was copy-pasted from Stack Overflow. No tutorials were followed. :D
The entire codebase — architecture, Qt signal wiring, audio engine, space animations, streaming integrations, alarm system, installer spec, test suite, CI pipeline — was grown in conversation, one idea at a time, between a person who knew what they wanted and an AI that knew how to build it.

That's the whole point. You don't need to know PySide6. 
You don't need to know PyInstaller. You don't need to have written a music player before. You just need a clear idea of what you want to exist in the world, and the willingness to iterate.

**Tonal is proof that the barrier to building real, native, polished desktop software is now just: having something worth building.**

---

## License

MIT — free to use, modify, and distribute. Feel free to fork, test, dismantle and just play ! :D 

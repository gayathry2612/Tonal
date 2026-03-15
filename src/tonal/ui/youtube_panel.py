"""
YouTube Music integration panel.

Requires:
  pip install ytmusicapi yt-dlp

Google Sign-In (Device Authorization Flow)
-------------------------------------------
No Google Cloud project is required.  Tonal uses the same embedded YouTube
TV app credentials that ytmusicapi uses internally, so the user only needs to:

  1. Click "Sign in with Google"
  2. Visit the short URL shown on screen (e.g. https://google.com/device)
  3. Enter the 8-character code
  4. Approve access in the browser

Tonal polls in a background QThread and detects completion automatically.
Tokens are cached in  ~/.tonal/youtube_oauth.json  and refreshed silently.

Unauthenticated search
-----------------------
Basic searching still works without signing in; authentication is needed for
personalised results (liked songs, recommendations, private playlists).

Playback
--------
Double-click extracts the best audio stream via yt-dlp (background QThread)
and loads it directly into the shared QMediaPlayer.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox,
    QProgressBar, QFrame, QApplication,
)
from PySide6.QtCore import Qt, Signal, Slot, QThread, QObject
from PySide6.QtGui import QColor, QDesktopServices, QClipboard
from PySide6.QtCore import QUrl

try:
    from ytmusicapi import YTMusic
    _YTMUSIC_OK = True
except ImportError:
    _YTMUSIC_OK = False

# ---------------------------------------------------------------------------
# Unauthenticated YTMusic singleton
# ---------------------------------------------------------------------------
# ytmusicapi ≥ 1.7 tries to load a gettext 'base' domain from its own
# locales directory.  On some installs (particularly venvs or conda envs)
# that directory is missing, raising:
#   [Errno 2] No translation file found for domain: 'base'
# We create one shared instance at import time so the error surfaces once
# and is caught, rather than crashing on every search call.

_ytm_unauth: "YTMusic | None" = None
_ytm_unauth_error: str = ""

def _get_unauth_ytm():
    """Return (or lazily create) a module-level unauthenticated YTMusic instance."""
    global _ytm_unauth, _ytm_unauth_error
    if _ytm_unauth is not None:
        return _ytm_unauth
    if _ytm_unauth_error:
        raise RuntimeError(_ytm_unauth_error)
    if not _YTMUSIC_OK:
        raise RuntimeError("ytmusicapi is not installed.")
    try:
        # language="en" skips the gettext locale lookup in ytmusicapi ≥ 1.7
        try:
            _ytm_unauth = YTMusic(language="en")
        except TypeError:
            # Older ytmusicapi versions don't accept the language kwarg
            _ytm_unauth = YTMusic()
        return _ytm_unauth
    except OSError as exc:
        if "translation file" in str(exc).lower() or "base" in str(exc).lower():
            _ytm_unauth_error = (
                "ytmusicapi locale files are missing.\n\n"
                "Fix:  pip install --force-reinstall ytmusicapi\n"
                "then restart Tonal."
            )
        else:
            _ytm_unauth_error = str(exc)
        raise RuntimeError(_ytm_unauth_error) from exc
    except Exception as exc:
        _ytm_unauth_error = str(exc)
        raise RuntimeError(_ytm_unauth_error) from exc

try:
    import yt_dlp  # noqa: F401
    _YTDLP_OK = True
except ImportError:
    _YTDLP_OK = False


# ---------------------------------------------------------------------------
# Google Device-flow constants
# (same credentials ytmusicapi embeds — the public YouTube TV app)
# ---------------------------------------------------------------------------

_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
_TOKEN_URL       = "https://oauth2.googleapis.com/token"
_USERINFO_URL    = "https://www.googleapis.com/oauth2/v1/userinfo"
_YT_SCOPE        = "https://www.googleapis.com/auth/youtube"
_DEVICE_GRANT    = "urn:ietf:params:oauth:grant-type:device_code"
_OAUTH_FILE      = Path.home() / ".tonal" / "youtube_oauth.json"

# Try ytmusicapi's bundled credentials first; fall back to the well-known values
try:
    from ytmusicapi.constants import OAUTH_CLIENT_ID     as _CLIENT_ID   # noqa
    from ytmusicapi.constants import OAUTH_CLIENT_SECRET as _CLIENT_SECRET  # noqa
except ImportError:
    # Public YouTube TV app credentials (used by ytmusicapi and many open tools)
    _CLIENT_ID     = "861556708454-d6dlm3lh05idd8npek18k6be8ba3oc68.apps.googleusercontent.com"
    _CLIENT_SECRET = "SboVhoG9s0rNafixCSGGKXAT"


# ---------------------------------------------------------------------------
# Device-flow worker  (background QThread)
# ---------------------------------------------------------------------------

class _DeviceFlowWorker(QObject):
    """
    Runs the Google Device Authorization Grant entirely in a background thread.

    Phase 1 — request device code → emits  code_ready(url, user_code, expires_in)
    Phase 2 — poll for token       → emits  auth_complete(token_json_str)
                                     or     auth_failed(error_message)
    """

    code_ready    = Signal(str, str, int)   # verification_url, user_code, expires_in
    auth_complete = Signal(str)             # JSON string of the full token response
    auth_failed   = Signal(str)             # human-readable error

    def __init__(self):
        super().__init__()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            import requests
        except ImportError:
            self.auth_failed.emit(
                "The 'requests' package is required.\n\nRun:  pip install requests"
            )
            return

        # ── Phase 1: obtain device code ───────────────────────────────
        try:
            resp = requests.post(
                _DEVICE_CODE_URL,
                data={"client_id": _CLIENT_ID, "scope": _YT_SCOPE},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.auth_failed.emit(f"Could not reach Google: {exc}")
            return

        device_code      = data["device_code"]
        user_code        = data["user_code"]
        verification_url = data.get("verification_url", "https://google.com/device")
        expires_in       = int(data.get("expires_in", 1800))
        interval         = int(data.get("interval", 5))

        self.code_ready.emit(verification_url, user_code, expires_in)

        # ── Phase 2: poll until the user approves ─────────────────────
        deadline = time.monotonic() + expires_in
        while time.monotonic() < deadline and not self._cancelled:
            time.sleep(interval)
            try:
                tok = requests.post(
                    _TOKEN_URL,
                    data={
                        "client_id":     _CLIENT_ID,
                        "client_secret": _CLIENT_SECRET,
                        "device_code":   device_code,
                        "grant_type":    _DEVICE_GRANT,
                    },
                    timeout=15,
                )
                td = tok.json()
            except Exception:
                continue

            error = td.get("error", "")
            if "access_token" in td:
                td["expires_at"] = int(time.time()) + int(td.get("expires_in", 3600))
                self.auth_complete.emit(json.dumps(td))
                return
            elif error == "authorization_pending":
                continue
            elif error == "slow_down":
                interval = min(interval + 5, 30)
            elif error == "expired_token":
                break
            else:
                self.auth_failed.emit(f"Authorization failed: {td.get('error_description', error)}")
                return

        if not self._cancelled:
            self.auth_failed.emit("Authorization timed out — please try signing in again.")


class _DeviceFlowThread(QThread):
    code_ready    = Signal(str, str, int)
    auth_complete = Signal(str)
    auth_failed   = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = _DeviceFlowWorker()

    def run(self) -> None:
        self._worker.code_ready.connect(self.code_ready)
        self._worker.auth_complete.connect(self.auth_complete)
        self._worker.auth_failed.connect(self.auth_failed)
        self._worker.run()

    def cancel(self) -> None:
        self._worker.cancel()


# ---------------------------------------------------------------------------
# Stream-extraction worker
# ---------------------------------------------------------------------------

class _StreamWorker(QObject):
    stream_ready  = Signal(str, dict)
    stream_failed = Signal(str)

    def __init__(self, video_id: str, track_info: dict):
        super().__init__()
        self._video_id   = video_id
        self._track_info = track_info

    def run(self) -> None:
        try:
            import yt_dlp as ytdlp
        except ImportError:
            self.stream_failed.emit("yt-dlp is not installed.  Run:  pip install yt-dlp")
            return

        url = f"https://www.youtube.com/watch?v={self._video_id}"
        ydl_opts = {
            "format":      "bestaudio[ext=m4a]/bestaudio/best",
            "quiet":       True,
            "no_warnings": True,
        }
        try:
            with ytdlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info.get("url")
                if not stream_url:
                    for fmt in reversed(info.get("formats", [])):
                        if fmt.get("acodec") != "none" and fmt.get("url"):
                            stream_url = fmt["url"]
                            break
                if stream_url:
                    self.stream_ready.emit(stream_url, self._track_info)
                else:
                    self.stream_failed.emit("No audio stream found for this video.")
        except Exception as exc:
            self.stream_failed.emit(str(exc))


class _StreamThread(QThread):
    stream_ready  = Signal(str, dict)
    stream_failed = Signal(str)

    def __init__(self, video_id: str, track_info: dict, parent=None):
        super().__init__(parent)
        self._worker = _StreamWorker(video_id, track_info)

    def run(self) -> None:
        self._worker.stream_ready.connect(self.stream_ready)
        self._worker.stream_failed.connect(self.stream_failed)
        self._worker.run()


# ---------------------------------------------------------------------------
# YouTubePanel
# ---------------------------------------------------------------------------

class YouTubePanel(QWidget):
    """
    YouTube Music search + playback panel with Google Sign-In.

    Signals
    -------
    play_requested(str, dict)   stream_url, track_info
    """

    play_requested = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results         : list[dict]           = []
        self._stream_threads  : list[_StreamThread]  = []
        self._auth_thread     : _DeviceFlowThread | None = None
        self._ytm             = None   # YTMusic instance (None = unauthenticated)
        self._user_email      : str    = ""

        self._build_ui()
        self._try_restore_session()

    # ── Session restore ───────────────────────────────────────────────

    def _try_restore_session(self) -> None:
        if not _YTMUSIC_OK or not _OAUTH_FILE.exists():
            return
        try:
            token_data = json.loads(_OAUTH_FILE.read_text(encoding="utf-8"))
            # Check not expired
            expires_at = token_data.get("expires_at", 0)
            if time.time() < expires_at or token_data.get("refresh_token"):
                self._ytm = self._make_ytm(token_data)
                # Fetch display name via userinfo
                email = self._fetch_userinfo(token_data.get("access_token", ""))
                self._set_signed_in(email or "your Google account")
        except Exception:
            pass

    def _make_ytm(self, token_data: dict):
        """Create a YTMusic instance from a token dict, handling API differences."""
        # Write a temp file then pass its path — the most reliable approach
        _OAUTH_FILE.write_text(json.dumps(token_data), encoding="utf-8")
        try:
            from ytmusicapi.auth.oauth import OAuthCredentials
            creds = OAuthCredentials(client_id=_CLIENT_ID, client_secret=_CLIENT_SECRET)
            return YTMusic(auth=str(_OAUTH_FILE), oauth_credentials=creds)
        except (ImportError, TypeError, Exception):
            try:
                return YTMusic(auth=str(_OAUTH_FILE))
            except Exception:
                return _get_unauth_ytm()  # fall back to shared unauthenticated instance

    def _fetch_userinfo(self, access_token: str) -> str:
        try:
            import requests
            r = requests.get(
                _USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=8,
            )
            return r.json().get("email", "")
        except Exception:
            return ""

    # ── Build UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # ── Header row ────────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        icon = QLabel("▶")
        icon.setStyleSheet("font-size: 22px; color: #ff0000;")
        title = QLabel("YouTube Music")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e8e8f0;")
        hdr_row.addWidget(icon)
        hdr_row.addWidget(title)
        hdr_row.addStretch(1)
        layout.addLayout(hdr_row)

        # ── Auth section ──────────────────────────────────────────────
        self._auth_section = self._build_auth_section()
        layout.addWidget(self._auth_section)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2d2d4e; margin: 2px 0;")
        layout.addWidget(sep)

        if not _YTMUSIC_OK or not _YTDLP_OK:
            missing = [p for p, ok in [("ytmusicapi", _YTMUSIC_OK), ("yt-dlp", _YTDLP_OK)] if not ok]
            warn = QLabel(
                f"Missing packages: {', '.join(missing)}\n\n"
                f"Run:  pip install {' '.join(missing)}\nthen restart Tonal."
            )
            warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            warn.setStyleSheet("color: #9090b0; font-size: 14px; padding: 40px;")
            layout.addWidget(warn)
            return

        # ── Search bar ────────────────────────────────────────────────
        search_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search YouTube Music…")
        self._search_box.setClearButtonEnabled(True)
        self._search_btn = QPushButton("Search")
        self._search_btn.setObjectName("btnSidebar")
        search_row.addWidget(self._search_box, 1)
        search_row.addWidget(self._search_btn)
        layout.addLayout(search_row)

        # ── Filter chips ──────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._filter_btns: dict[str, QPushButton] = {}
        for label, key in [("Songs", "songs"), ("Videos", "videos"), ("Albums", "albums")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == "songs")
            btn.setObjectName("btnSidebar")
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            self._filter_btns[key] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch(1)
        self._active_filter = "songs"
        layout.addLayout(filter_row)

        # ── Status + loading bar ──────────────────────────────────────
        self._results_lbl = QLabel("Search to discover music")
        self._results_lbl.setObjectName("statusLabel")
        layout.addWidget(self._results_lbl)

        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)
        self._loading_bar.setFixedHeight(2)
        self._loading_bar.setTextVisible(False)
        self._loading_bar.setStyleSheet(
            "QProgressBar { background: transparent; border: none; }"
            "QProgressBar::chunk { background: #7c6af7; }"
        )
        self._loading_bar.hide()
        layout.addWidget(self._loading_bar)

        # ── Results table ─────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(3, 60)
        self._table.verticalHeader().setDefaultSectionSize(34)
        layout.addWidget(self._table, 1)

        hint = QLabel("Double-click to stream  ·  Audio via yt-dlp  ·  Sign in for personalised results")
        hint.setStyleSheet("font-size: 11px; color: #60607a; padding: 4px;")
        layout.addWidget(hint)

        # Wire
        self._search_btn.clicked.connect(self._on_search)
        self._search_box.returnPressed.connect(self._on_search)
        self._table.cellDoubleClicked.connect(self._on_double_click)

    # ── Auth section widget ───────────────────────────────────────────

    def _build_auth_section(self) -> QWidget:
        """Returns a compact row that switches between sign-in and signed-in states."""
        container = QWidget()
        container.setFixedHeight(42)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        # Google "G" logo approximation
        g_lbl = QLabel("G")
        g_lbl.setFixedSize(26, 26)
        g_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        g_lbl.setStyleSheet(
            "background: white; color: #4285F4; font-size: 15px; font-weight: bold;"
            " border-radius: 13px;"
        )
        row.addWidget(g_lbl)

        # ── Not signed in ─────────────────────────────────────────────
        self._signin_btn = QPushButton("Sign in with Google")
        self._signin_btn.setStyleSheet(
            "QPushButton { background: #4285F4; color: white; border: none;"
            " border-radius: 4px; font-size: 13px; font-weight: 600;"
            " padding: 6px 18px; }"
            "QPushButton:hover  { background: #5a95f5; }"
            "QPushButton:pressed{ background: #2f6de1; }"
        )
        self._signin_btn.clicked.connect(self._on_signin)
        row.addWidget(self._signin_btn)

        # ── Signed in ─────────────────────────────────────────────────
        self._account_lbl = QLabel("")
        self._account_lbl.setStyleSheet("color: #9090b0; font-size: 12px;")
        self._account_lbl.hide()
        row.addWidget(self._account_lbl)

        self._signout_btn = QPushButton("Sign out")
        self._signout_btn.setObjectName("btnSidebar")
        self._signout_btn.clicked.connect(self._on_signout)
        self._signout_btn.hide()
        row.addWidget(self._signout_btn)

        # ── Signing-in progress info ──────────────────────────────────
        self._device_info_widget = self._build_device_info_widget()
        self._device_info_widget.hide()
        row.addWidget(self._device_info_widget)

        row.addStretch(1)
        return container

    def _build_device_info_widget(self) -> QWidget:
        """Inline widget shown while waiting for the user to authorise in their browser."""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._device_url_lbl = QLabel("")
        self._device_url_lbl.setStyleSheet(
            "color: #7c6af7; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(self._device_url_lbl)

        self._device_code_lbl = QLabel("")
        self._device_code_lbl.setStyleSheet(
            "color: #e8e8f0; font-size: 13px; font-weight: bold;"
            " background: #2d2d4e; border-radius: 4px; padding: 2px 10px;"
        )
        layout.addWidget(self._device_code_lbl)

        copy_btn = QPushButton("Copy code")
        copy_btn.setObjectName("btnSidebar")
        copy_btn.setFixedHeight(26)
        copy_btn.clicked.connect(self._copy_device_code)
        layout.addWidget(copy_btn)

        open_btn = QPushButton("Open URL")
        open_btn.setObjectName("btnSidebar")
        open_btn.setFixedHeight(26)
        open_btn.clicked.connect(self._open_device_url)
        layout.addWidget(open_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("btnSidebar")
        cancel_btn.setFixedHeight(26)
        cancel_btn.clicked.connect(self._cancel_signin)
        layout.addWidget(cancel_btn)

        return w

    # ── Auth state helpers ────────────────────────────────────────────

    def _set_signed_in(self, email: str) -> None:
        self._user_email = email
        self._signin_btn.hide()
        self._device_info_widget.hide()
        self._account_lbl.setText(f"● Signed in as  {email}")
        self._account_lbl.show()
        self._signout_btn.show()

    def _set_signed_out(self) -> None:
        self._user_email = ""
        self._account_lbl.hide()
        self._signout_btn.hide()
        self._device_info_widget.hide()
        self._signin_btn.show()

    # ── Sign-in flow ──────────────────────────────────────────────────

    @Slot()
    def _on_signin(self) -> None:
        if not _YTMUSIC_OK:
            QMessageBox.warning(self, "ytmusicapi missing",
                                "Install ytmusicapi first:\n\n  pip install ytmusicapi")
            return

        self._signin_btn.setEnabled(False)

        self._auth_thread = _DeviceFlowThread(self)
        self._auth_thread.code_ready.connect(self._on_code_ready)
        self._auth_thread.auth_complete.connect(self._on_auth_complete)
        self._auth_thread.auth_failed.connect(self._on_auth_failed)
        self._auth_thread.finished.connect(self._auth_thread.deleteLater)
        self._auth_thread.start()

    @Slot(str, str, int)
    def _on_code_ready(self, verification_url: str, user_code: str, expires_in: int) -> None:
        self._current_device_url  = verification_url
        self._current_device_code = user_code
        self._device_url_lbl.setText(f"Go to  {verification_url}  and enter:")
        self._device_code_lbl.setText(user_code)
        self._signin_btn.hide()
        self._device_info_widget.show()

    @Slot(str)
    def _on_auth_complete(self, token_json: str) -> None:
        try:
            token_data = json.loads(token_json)
            _OAUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            _OAUTH_FILE.write_text(token_json, encoding="utf-8")
            self._ytm = self._make_ytm(token_data)
            email = self._fetch_userinfo(token_data.get("access_token", ""))
            self._set_signed_in(email or "your Google account")
            self._signin_btn.setEnabled(True)
        except Exception as exc:
            self._on_auth_failed(str(exc))

    @Slot(str)
    def _on_auth_failed(self, msg: str) -> None:
        self._set_signed_out()
        self._signin_btn.setEnabled(True)
        QMessageBox.warning(self, "Google Sign-In Failed", msg)

    @Slot()
    def _cancel_signin(self) -> None:
        if self._auth_thread:
            self._auth_thread.cancel()
        self._set_signed_out()
        self._signin_btn.setEnabled(True)

    @Slot()
    def _on_signout(self) -> None:
        self._ytm = None
        if _OAUTH_FILE.exists():
            _OAUTH_FILE.unlink(missing_ok=True)
        self._set_signed_out()

    @Slot()
    def _copy_device_code(self) -> None:
        QApplication.clipboard().setText(self._current_device_code)

    @Slot()
    def _open_device_url(self) -> None:
        QDesktopServices.openUrl(QUrl(self._current_device_url))

    # ── Filter ────────────────────────────────────────────────────────

    def _set_filter(self, key: str) -> None:
        self._active_filter = key
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == key)

    # ── Search ────────────────────────────────────────────────────────

    @Slot()
    def _on_search(self) -> None:
        if not _YTMUSIC_OK:
            return
        q = self._search_box.text().strip()
        if not q:
            return
        self._results_lbl.setText("Searching…")
        try:
            results = self.search(q, filter_type=self._active_filter)
        except RuntimeError as exc:
            msg = str(exc)
            self._results_lbl.setText("Search error — see details")
            QMessageBox.warning(self, "YouTube Music Search Error", msg)
            return
        except Exception as exc:
            self._results_lbl.setText(f"Error: {exc}")
            return
        self._populate_table(results)

    def search(self, query: str, filter_type: str = "songs", limit: int = 30) -> list[dict]:
        """Public: search YouTube Music.  Uses authenticated YTMusic if signed in."""
        if not _YTMUSIC_OK:
            return []
        ytm = self._ytm if self._ytm else _get_unauth_ytm()
        raw = ytm.search(query, filter=filter_type, limit=limit)
        tracks = []
        for item in raw:
            video_id = item.get("videoId")
            if not video_id:
                continue
            artists    = item.get("artists") or []
            artist     = ", ".join(a.get("name", "") for a in artists if a.get("name"))
            album_info = item.get("album") or {}
            album      = album_info.get("name", "") if isinstance(album_info, dict) else ""
            tracks.append({
                "source":   "youtube",
                "video_id": video_id,
                "title":    item.get("title", ""),
                "artist":   artist,
                "album":    album,
                "duration": item.get("duration") or "",
            })
        self._results = tracks
        return tracks

    def _populate_table(self, tracks: list[dict]) -> None:
        self._table.setRowCount(0)
        for i, t in enumerate(tracks):
            self._table.insertRow(i)
            for col, key in enumerate(["title", "artist", "album", "duration"]):
                item = QTableWidgetItem(t.get(key, ""))
                item.setForeground(QColor("#9090b0"))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, t)
                self._table.setItem(i, col, item)
        plural = "s" if len(tracks) != 1 else ""
        self._results_lbl.setText(f"{len(tracks)} result{plural}")

    # ── Playback ──────────────────────────────────────────────────────

    @Slot(int, int)
    def _on_double_click(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if not item:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        if not track:
            return
        if not _YTDLP_OK:
            QMessageBox.warning(
                self, "yt-dlp not installed",
                "Install yt-dlp to enable playback:\n\n  pip install yt-dlp"
            )
            return

        self._results_lbl.setText(f"Loading  {track.get('title', '')}…")
        self._loading_bar.show()
        self._search_btn.setEnabled(False)

        thread = _StreamThread(track["video_id"], track, self)
        thread.stream_ready.connect(self._on_stream_ready)
        thread.stream_failed.connect(self._on_stream_failed)
        thread.finished.connect(thread.deleteLater)
        self._stream_threads.append(thread)
        thread.start()

    @Slot(str, dict)
    def _on_stream_ready(self, url: str, track: dict) -> None:
        self._loading_bar.hide()
        self._search_btn.setEnabled(True)
        self._results_lbl.setText(
            f"Playing  {track.get('title', '')}  —  {track.get('artist', '')}"
        )
        self.play_requested.emit(url, track)

    @Slot(str)
    def _on_stream_failed(self, msg: str) -> None:
        self._loading_bar.hide()
        self._search_btn.setEnabled(True)
        self._results_lbl.setText("Stream extraction failed")
        QMessageBox.warning(self, "Playback Error", msg)

    def _on_stream_ready_from_alarm(self, video_id: str, track: dict) -> None:
        """Called by MainWindow when an alarm fires for a YouTube track."""
        if not _YTDLP_OK:
            return
        thread = _StreamThread(video_id, track, self)
        thread.stream_ready.connect(self._on_stream_ready)
        thread.stream_failed.connect(self._on_stream_failed)
        thread.finished.connect(thread.deleteLater)
        self._stream_threads.append(thread)
        thread.start()

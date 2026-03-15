"""
Spotify integration panel.

Requires the ``spotipy`` package (``pip install spotipy``).

Authentication flow
-------------------
1. Create a free Spotify Developer App at https://developer.spotify.com/dashboard
2. In the app's Edit Settings → Redirect URIs, add:
       https://localhost/callback
   (Spotify now requires HTTPS even for localhost)
3. Enter the Client ID, Client Secret, and that exact Redirect URI in Tonal
4. Click "Connect" → browser opens the Spotify auth page
5. Click Allow; the browser redirects to https://localhost/callback and shows a
   connection error — this is expected because there is no server there
6. Copy the full URL from the address bar and paste it into the Tonal field
7. Tonal extracts the code, exchanges it for tokens, and caches them in
   ~/.tonal/spotify_cache.json; subsequent launches refresh the token silently

Playback
--------
Double-clicking a search result calls  sp.start_playback(uris=[...])
via the Spotify Connect API, which plays the track on the user's active
Spotify device (desktop app, web player, phone, etc.).
Requires Spotify Premium.

Search results are also exposed via  search(query) -> list[dict]  for use
in the alarm song-selector.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QStackedWidget,
    QMessageBox, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, Slot, QThread, QObject, QUrl, QTimer
from PySide6.QtGui import QColor, QDesktopServices

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth   # requires client_id + client_secret
    _SPOTIPY_OK = True
except ImportError:
    _SPOTIPY_OK = False


_SCOPE = (
    "user-read-private "           # required for market=from_token in search
    "user-read-email "
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "streaming"
)
_DEFAULT_REDIRECT_URI = "https://localhost/callback"
_CONFIG_FILE  = Path.home() / ".tonal" / "spotify_config.json"
_CACHE_FILE   = Path.home() / ".tonal" / "spotify_cache.json"


# ---------------------------------------------------------------------------
# OAuth callback HTTP server (runs in a QThread)
# ---------------------------------------------------------------------------

class _OAuthWorker(QObject):
    """Listens on a local port for the Spotify OAuth callback."""

    code_received = Signal(str)   # authorization code
    error         = Signal(str)

    def __init__(self, redirect_uri: str = _DEFAULT_REDIRECT_URI):
        super().__init__()
        parsed = urlparse(redirect_uri)
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 8080

    def run(self) -> None:
        from http.server import HTTPServer, BaseHTTPRequestHandler

        received = {"code": None}

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                params = parse_qs(urlparse(self.path).query)
                if "code" in params:
                    received["code"] = params["code"][0]
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body style='font-family:sans-serif;"
                        b"background:#0f0f1e;color:#e8e8f0;text-align:center;"
                        b"padding:60px'><h2>Authorization successful!</h2>"
                        b"<p>You can close this window and return to Tonal.</p>"
                        b"</body></html>"
                    )
                elif "error" in params:
                    received["code"] = "__error__"
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Authorization failed.")

            def log_message(self, *_args):
                pass  # suppress server logs

        try:
            server = HTTPServer((self._host, self._port), _Handler)
            server.timeout = 120           # wait up to 2 minutes
            server.handle_request()        # handle exactly one request
        except Exception as exc:
            self.error.emit(str(exc))
            return

        code = received["code"]
        if code and code != "__error__":
            self.code_received.emit(code)
        else:
            self.error.emit("Authorization was cancelled or failed.")


class _OAuthThread(QThread):
    code_received = Signal(str)
    error         = Signal(str)

    def __init__(self, redirect_uri: str = _DEFAULT_REDIRECT_URI, parent=None):
        super().__init__(parent)
        self._worker = _OAuthWorker(redirect_uri)

    def run(self) -> None:
        self._worker.code_received.connect(self.code_received)
        self._worker.error.connect(self.error)
        self._worker.run()


# ---------------------------------------------------------------------------
# SpotifyPanel
# ---------------------------------------------------------------------------

class SpotifyPanel(QWidget):
    """
    Full Spotify integration panel with auth flow, search, and playback.

    Signals
    -------
    play_requested(dict)
        Emitted when the user double-clicks a result.
        The dict contains  {"source": "spotify", "spotify_uri": ..., ...}
    search_result(list)
        Public: last search results as list[dict] — used by AlarmDialog
    """

    play_requested = Signal(dict)

    def __init__(self, data_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self._data_dir   = data_dir or (Path.home() / ".tonal")
        self._config     = self._load_config()
        self._sp           = None          # spotipy.Spotify instance
        self._oauth        = None          # SpotifyOAuth instance
        self._results      : list[dict] = []
        self._oauth_thread : _OAuthThread | None = None
        self._user_country : str = ""    # ISO 3166-1 alpha-2, e.g. "IN" or "US"
        self._is_playing   : bool = False  # mirrors Spotify playback state

        # Poll Spotify every 5 s to keep transport controls in sync
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(5_000)
        self._poll_timer.timeout.connect(self._poll_playback)

        self._build_ui()
        self._try_restore_session()

    # ── Config persistence ────────────────────────────────────────────

    def _load_config(self) -> dict:
        p = self._data_dir / "spotify_config.json"
        cfg: dict = {}
        if p.exists():
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        # Migrate: old default used http://localhost:8080 which Spotify now rejects.
        # Replace silently so the field shows the current safe default on next open.
        old_insecure = ("http://localhost:8080/callback", "http://localhost/callback")
        if cfg.get("redirect_uri", "") in old_insecure:
            cfg["redirect_uri"] = _DEFAULT_REDIRECT_URI
            try:
                p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            except Exception:
                pass
        return cfg

    def _save_config(self) -> None:
        p = self._data_dir / "spotify_config.json"
        try:
            p.write_text(json.dumps(self._config, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── Build UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_auth_page())    # index 0
        self._stack.addWidget(self._build_search_page())  # index 1

    # ── Auth page ─────────────────────────────────────────────────────

    def _build_auth_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        if not _SPOTIPY_OK:
            msg = QLabel(
                "spotipy is not installed.\n\n"
                "Run:  pip install spotipy\n"
                "then restart Tonal."
            )
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setStyleSheet("color: #60607a; font-size: 14px;")
            layout.addWidget(msg)
            return page

        icon = QLabel("🎧")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon)

        title = QLabel("Spotify Integration")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #e8e8f0;")
        layout.addWidget(title)

        sub = QLabel(
            "Connect your Spotify Premium account to search and play music.\n"
            "You need a free Spotify Developer app — see instructions below."
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: #9090b0; font-size: 13px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # Setup instructions link
        instr_btn = QPushButton("📋  How to get a Client ID")
        instr_btn.setObjectName("btnSidebar")
        instr_btn.setFixedWidth(220)
        instr_btn.clicked.connect(self._open_dev_docs)
        layout.addWidget(instr_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedWidth(300)
        sep.setStyleSheet("color: #2d2d4e;")
        layout.addWidget(sep, alignment=Qt.AlignmentFlag.AlignCenter)

        # Credentials grid: Client ID + Client Secret + Redirect URI
        from PySide6.QtWidgets import QFormLayout
        creds_box = QWidget()
        creds_box.setFixedWidth(420)
        creds_layout = QFormLayout(creds_box)
        creds_layout.setContentsMargins(0, 0, 0, 0)
        creds_layout.setSpacing(8)
        creds_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._client_id_edit = QLineEdit(self._config.get("client_id", ""))
        self._client_id_edit.setPlaceholderText("32-character Client ID")
        creds_layout.addRow("Client ID", self._client_id_edit)

        self._client_secret_edit = QLineEdit(self._config.get("client_secret", ""))
        self._client_secret_edit.setPlaceholderText("Client Secret")
        self._client_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        creds_layout.addRow("Client Secret", self._client_secret_edit)

        self._redirect_uri_edit = QLineEdit(
            self._config.get("redirect_uri", _DEFAULT_REDIRECT_URI)
        )
        self._redirect_uri_edit.setPlaceholderText("https://localhost/callback")
        creds_layout.addRow("Redirect URI", self._redirect_uri_edit)

        layout.addWidget(creds_box, alignment=Qt.AlignmentFlag.AlignCenter)

        redirect_note = QLabel(
            "Step 1 — In your Spotify Developer Dashboard → Edit Settings → Redirect URIs\n"
            "add exactly:  https://localhost/callback  (HTTPS is required by Spotify)\n\n"
            "Step 2 — Make sure the Redirect URI field above matches that value exactly."
        )
        redirect_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        redirect_note.setStyleSheet(
            "font-size: 11px; color: #70708a; background: #1a1a2e;"
            "border: 1px solid #2d2d4e; border-radius: 6px; padding: 8px;"
        )
        redirect_note.setWordWrap(True)
        redirect_note.setFixedWidth(420)
        layout.addWidget(redirect_note, alignment=Qt.AlignmentFlag.AlignCenter)

        self._connect_btn = QPushButton("Connect to Spotify")
        self._connect_btn.setObjectName("btnConnect")
        self._connect_btn.setFixedSize(200, 40)
        self._connect_btn.setStyleSheet(
            "QPushButton#btnConnect { background: #1DB954; color: white;"
            " border-radius: 20px; font-size: 14px; font-weight: bold; }"
            "QPushButton#btnConnect:hover { background: #1ed760; }"
            "QPushButton#btnConnect:disabled { background: #2d2d4e; color: #60607a; }"
        )
        self._connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(self._connect_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._auth_status_lbl = QLabel("")
        self._auth_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._auth_status_lbl.setStyleSheet("font-size: 12px; color: #9090b0;")
        layout.addWidget(self._auth_status_lbl)

        # ── Paste-back panel (shown after browser opens) ──────────────
        self._paste_panel = QWidget()
        self._paste_panel.setFixedWidth(420)
        self._paste_panel.hide()
        paste_layout = QVBoxLayout(self._paste_panel)
        paste_layout.setContentsMargins(0, 0, 0, 0)
        paste_layout.setSpacing(6)

        paste_sep = QFrame()
        paste_sep.setFrameShape(QFrame.Shape.HLine)
        paste_sep.setStyleSheet("color: #2d2d4e;")
        paste_layout.addWidget(paste_sep)

        paste_lbl = QLabel(
            "After clicking Allow in the browser, Spotify redirects to your Redirect URI.\n"
            "The browser will show a connection error — that's normal.\n"
            "Copy the full URL from the address bar and paste it here:"
        )
        paste_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        paste_lbl.setStyleSheet("font-size: 12px; color: #9090b0;")
        paste_lbl.setWordWrap(True)
        paste_layout.addWidget(paste_lbl)

        paste_row = QHBoxLayout()
        self._paste_url_edit = QLineEdit()
        self._paste_url_edit.setPlaceholderText("https://localhost/callback?code=…")
        self._paste_url_edit.returnPressed.connect(self._on_paste_submit)
        paste_row.addWidget(self._paste_url_edit, 1)

        paste_submit = QPushButton("Submit")
        paste_submit.setObjectName("btnSidebar")
        paste_submit.clicked.connect(self._on_paste_submit)
        paste_row.addWidget(paste_submit)
        paste_layout.addLayout(paste_row)

        layout.addWidget(self._paste_panel, alignment=Qt.AlignmentFlag.AlignCenter)

        return page

    # ── Search page ───────────────────────────────────────────────────

    def _build_search_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Status bar
        status_row = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #1DB954; font-size: 16px;")
        self._status_name = QLabel("Connected")
        self._status_name.setStyleSheet("color: #9090b0; font-size: 12px;")
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_name)
        status_row.addStretch(1)
        disconnect_btn = QPushButton("Disconnect")
        disconnect_btn.setObjectName("btnSidebar")
        disconnect_btn.clicked.connect(self._on_disconnect)
        status_row.addWidget(disconnect_btn)
        layout.addLayout(status_row)

        # Search bar
        search_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search Spotify…")
        self._search_box.setClearButtonEnabled(True)
        self._search_btn = QPushButton("Search")
        self._search_btn.setObjectName("btnSidebar")
        search_row.addWidget(self._search_box, 1)
        search_row.addWidget(self._search_btn)
        layout.addLayout(search_row)

        # Results info
        self._results_lbl = QLabel("Search to discover music")
        self._results_lbl.setObjectName("statusLabel")
        layout.addWidget(self._results_lbl)

        # Results table
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

        # ── Transport bar ─────────────────────────────────────────────
        transport_frame = QFrame()
        transport_frame.setStyleSheet(
            "QFrame { background: #13131f; border-top: 1px solid #2d2d4e;"
            " border-radius: 0px; }"
        )
        transport_layout = QVBoxLayout(transport_frame)
        transport_layout.setContentsMargins(12, 8, 12, 8)
        transport_layout.setSpacing(4)

        # Now-playing label
        self._now_playing_lbl = QLabel("Nothing playing")
        self._now_playing_lbl.setStyleSheet(
            "font-size: 12px; color: #9090b0; background: transparent; border: none;"
        )
        self._now_playing_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._now_playing_lbl.setWordWrap(False)
        transport_layout.addWidget(self._now_playing_lbl)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addStretch(1)

        _btn_style = (
            "QPushButton { background: #1a1a2e; color: #e8e8f0; border: 1px solid #2d2d4e;"
            " border-radius: 16px; font-size: 16px; min-width: 32px; min-height: 32px; }"
            "QPushButton:hover { background: #2d2d4e; }"
            "QPushButton:disabled { color: #3a3a5a; border-color: #1d1d30; }"
        )

        self._prev_btn = QPushButton("⏮")
        self._prev_btn.setFixedSize(32, 32)
        self._prev_btn.setStyleSheet(_btn_style)
        self._prev_btn.setToolTip("Previous track")
        self._prev_btn.clicked.connect(self._on_prev)
        btn_row.addWidget(self._prev_btn)

        self._playpause_btn = QPushButton("▶")
        self._playpause_btn.setFixedSize(40, 40)
        self._playpause_btn.setStyleSheet(
            "QPushButton { background: #1DB954; color: white; border: none;"
            " border-radius: 20px; font-size: 16px; min-width: 40px; min-height: 40px; }"
            "QPushButton:hover { background: #1ed760; }"
            "QPushButton:disabled { background: #1a1a2e; color: #3a3a5a; }"
        )
        self._playpause_btn.setToolTip("Play / Pause")
        self._playpause_btn.clicked.connect(self._on_playpause)
        btn_row.addWidget(self._playpause_btn)

        self._next_btn = QPushButton("⏭")
        self._next_btn.setFixedSize(32, 32)
        self._next_btn.setStyleSheet(_btn_style)
        self._next_btn.setToolTip("Next track")
        self._next_btn.clicked.connect(self._on_next)
        btn_row.addWidget(self._next_btn)

        self._stop_btn = QPushButton("■")
        self._stop_btn.setFixedSize(32, 32)
        self._stop_btn.setStyleSheet(_btn_style)
        self._stop_btn.setToolTip("Stop (pause and return to start)")
        self._stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self._stop_btn)

        btn_row.addStretch(1)
        transport_layout.addLayout(btn_row)
        layout.addWidget(transport_frame)

        self._set_transport_enabled(False)

        # Wire
        self._search_btn.clicked.connect(self._on_search)
        self._search_box.returnPressed.connect(self._on_search)
        self._table.cellDoubleClicked.connect(self._on_double_click)

        return page

    # ── Session restore ───────────────────────────────────────────────

    def _try_restore_session(self) -> None:
        if not _SPOTIPY_OK:
            return
        client_id     = self._config.get("client_id",     "").strip()
        client_secret = self._config.get("client_secret", "").strip()
        redirect_uri  = self._config.get("redirect_uri",  _DEFAULT_REDIRECT_URI).strip()
        if not client_id or not client_secret:
            return
        cache = self._data_dir / "spotify_cache.json"
        if not cache.exists():
            return
        try:
            oauth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=_SCOPE,
                cache_path=str(cache),
                open_browser=False,
            )
            token_info = oauth.get_cached_token()
            if token_info:
                # Check that the cached token covers every scope we now require.
                # If scopes were added since the token was issued, delete the
                # cache so the user re-authenticates with the full scope set.
                cached_scopes = set(token_info.get("scope", "").split())
                required_scopes = set(_SCOPE.split())
                if not required_scopes.issubset(cached_scopes):
                    cache.unlink(missing_ok=True)
                    return   # Stay on auth page; user must reconnect
                self._oauth = oauth
                self._sp    = spotipy.Spotify(auth_manager=oauth)
                me = self._sp.me()
                self._user_country = me.get("country", "")
                self._status_name.setText(
                    f"Connected as  {me.get('display_name', 'Unknown')}"
                )
                self._stack.setCurrentIndex(1)
                self._poll_playback()     # immediate first fetch
                self._poll_timer.start()
        except Exception:
            pass  # Cache stale or invalid — stay on auth page

    # ── OAuth flow ────────────────────────────────────────────────────

    @Slot()
    def _on_connect(self) -> None:
        if not _SPOTIPY_OK:
            return
        client_id     = self._client_id_edit.text().strip()
        client_secret = self._client_secret_edit.text().strip()
        redirect_uri  = self._redirect_uri_edit.text().strip() or _DEFAULT_REDIRECT_URI
        if not client_id:
            QMessageBox.warning(self, "Missing Client ID",
                                "Please enter your Spotify Client ID.")
            return
        if not client_secret:
            QMessageBox.warning(self, "Missing Client Secret",
                                "Please enter your Spotify Client Secret.")
            return

        self._config["client_id"]     = client_id
        self._config["client_secret"] = client_secret
        self._config["redirect_uri"]  = redirect_uri
        self._save_config()

        cache = self._data_dir / "spotify_cache.json"
        try:
            self._oauth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=_SCOPE,
                cache_path=str(cache),
                open_browser=False,
            )
        except Exception as e:
            QMessageBox.critical(self, "Spotify Error", str(e))
            return

        auth_url = self._oauth.get_authorize_url()
        self._connect_btn.setEnabled(False)
        self._paste_panel.show()
        self._paste_url_edit.clear()

        # Start local callback server only when the redirect URI uses plain http
        # and points to localhost / 127.0.0.1 (auto-capture flow).
        parsed_redir = urlparse(redirect_uri)
        is_local_http = (
            parsed_redir.scheme == "http"
            and parsed_redir.hostname in ("localhost", "127.0.0.1")
        )
        if is_local_http:
            self._auth_status_lbl.setText("Browser opened — waiting for callback…")
            self._oauth_thread = _OAuthThread(redirect_uri, self)
            self._oauth_thread.code_received.connect(self._on_code_received)
            self._oauth_thread.error.connect(self._on_auth_error)
            self._oauth_thread.start()
        else:
            self._auth_status_lbl.setText(
                "Browser opened — authorise, then paste the redirect URL below."
            )

        # Open browser
        QDesktopServices.openUrl(QUrl(auth_url))

    @Slot()
    def _on_paste_submit(self) -> None:
        """Extract the auth code from a pasted redirect URL and complete auth."""
        raw = self._paste_url_edit.text().strip()
        if not raw:
            return
        # Accept either a full URL or a bare code
        if raw.startswith("http"):
            params = parse_qs(urlparse(raw).query)
            code = params.get("code", [None])[0]
            if not code:
                error = params.get("error", ["Unknown error"])[0]
                self._on_auth_error(f"Spotify returned: {error}")
                return
        else:
            code = raw   # user pasted just the code value
        self._on_code_received(code)

    @Slot(str)
    def _on_code_received(self, code: str) -> None:
        # Stop the local server thread if it's still running
        if self._oauth_thread and self._oauth_thread.isRunning():
            self._oauth_thread.quit()
        try:
            # Exchange auth code → tokens; SpotifyOAuth caches + auto-refreshes.
            self._oauth.get_access_token(code, check_cache=False)
            self._sp = spotipy.Spotify(auth_manager=self._oauth)
            me       = self._sp.me()
            self._user_country = me.get("country", "")
            name     = me.get("display_name", "Unknown")
            self._status_name.setText(f"Connected as  {name}")
            self._stack.setCurrentIndex(1)
            self._poll_playback()
            self._poll_timer.start()
        except Exception as exc:
            self._on_auth_error(str(exc))
        finally:
            self._connect_btn.setEnabled(True)
            self._auth_status_lbl.setText("")
            self._paste_panel.hide()

    @Slot(str)
    def _on_auth_error(self, msg: str) -> None:
        self._connect_btn.setEnabled(True)
        self._auth_status_lbl.setText(f"Error: {msg}")
        self._paste_panel.hide()
        QMessageBox.warning(self, "Spotify Auth Failed", msg)

    @Slot()
    def _on_disconnect(self) -> None:
        self._poll_timer.stop()
        self._sp    = None
        self._oauth = None
        self._is_playing = False
        cache = self._data_dir / "spotify_cache.json"
        if cache.exists():
            cache.unlink(missing_ok=True)
        self._stack.setCurrentIndex(0)

    # ── Search ────────────────────────────────────────────────────────

    @Slot()
    def _on_search(self) -> None:
        q = self._search_box.text().strip()
        if not q or not self._sp:
            return
        if len(q) < 2:
            self._results_lbl.setText("Please enter at least 2 characters.")
            return
        self._results_lbl.setText("Searching…")
        try:
            results = self.search(q)
        except Exception as exc:
            self._results_lbl.setText(f"Error: {exc}")
            QMessageBox.warning(self, "Spotify Search Error", str(exc))
            return
        self._populate_table(results)

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Public: search Spotify and return normalised track dicts.

        We bypass spotipy's search() wrapper and call the Spotify REST API
        directly.  Some spotipy releases serialise parameters in a way the
        current Spotify API rejects (returning 400 "Invalid limit"), whereas a
        raw requests call with the same parameters succeeds.  We still use
        spotipy's _auth_headers() so token refresh happens automatically.
        """
        if not self._sp or not _REQUESTS_OK:
            return []

        try:
            headers = self._sp._auth_headers()
        except Exception:
            headers = {}

        # Spotify search params.  Attempt order:
        #   1. q + type + limit + market  (full)
        #   2. q + type + limit           (drop market on 400)
        #   3. q + type                   (drop limit as last resort)
        base_params: dict = {"q": query, "type": "track", "limit": str(limit)}
        if self._user_country:
            base_params["market"] = self._user_country

        params = dict(base_params)
        resp = _requests.get(
            "https://api.spotify.com/v1/search",
            headers=headers, params=params, timeout=10,
        )
        if resp.status_code == 400 and "market" in params:
            params.pop("market")
            resp = _requests.get(
                "https://api.spotify.com/v1/search",
                headers=headers, params=params, timeout=10,
            )
        if resp.status_code == 400 and "limit" in params:
            params.pop("limit")
            resp = _requests.get(
                "https://api.spotify.com/v1/search",
                headers=headers, params=params, timeout=10,
            )

        if not resp.ok:
            try:
                err    = resp.json().get("error", {})
                msg    = err.get("message", resp.text)
                reason = err.get("reason", "")
                detail = f"{msg} (reason: {reason})" if reason else msg
            except Exception:
                detail = resp.text
            raise RuntimeError(
                f"Spotify search failed ({resp.status_code}): {detail}\n"
                f"URL tried: {resp.url}\n"
                f"Raw body: {resp.text[:300]}"
            )

        raw = resp.json()
        tracks = []
        for item in raw.get("tracks", {}).get("items", []):
            tracks.append({
                "source":      "spotify",
                "spotify_uri": item["uri"],
                "title":       item["name"],
                "artist":      ", ".join(a["name"] for a in item["artists"]),
                "album":       item["album"]["name"],
                "duration":    _ms_to_mmss(item["duration_ms"]),
                "duration_ms": item["duration_ms"],
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
        if not track or not self._sp:
            return

        # Emit for local player / alarm integration
        self.play_requested.emit(track)

        # Use Spotify Connect API to start playback on the active device
        try:
            self._sp.start_playback(uris=[track["spotify_uri"]])
            self._is_playing = True
            self._update_playpause_icon()
            self._set_transport_enabled(True)
            self._now_playing_lbl.setText(
                f"♫  {track.get('title', '')}  —  {track.get('artist', '')}"
            )
            QTimer.singleShot(1200, self._poll_playback)  # confirm with real state
        except spotipy.SpotifyException as exc:
            if exc.http_status == 404:
                self._handle_no_device(track["spotify_uri"])
            elif exc.http_status == 403:
                QMessageBox.information(
                    self,
                    "Spotify Premium Required",
                    "Playback control requires a Spotify Premium subscription.",
                )
            else:
                QMessageBox.warning(self, "Playback Error", str(exc))

    def _handle_no_device(self, uri: str) -> None:
        """Show available devices or prompt to open Spotify when none are active."""
        # Fetch the list of available devices from Spotify
        devices: list[dict] = []
        try:
            result  = self._sp.devices()
            devices = result.get("devices", [])
        except Exception:
            pass

        if devices:
            # Build a picker dialog so the user can choose which device to use
            from PySide6.QtWidgets import QDialog, QListWidget, QDialogButtonBox
            dlg = QDialog(self)
            dlg.setWindowTitle("Choose a Spotify Device")
            dlg.setMinimumWidth(320)
            dlg_layout = QVBoxLayout(dlg)

            lbl = QLabel("Select a device to play on:")
            lbl.setStyleSheet("color: #e8e8f0;")
            dlg_layout.addWidget(lbl)

            lst = QListWidget()
            lst.setStyleSheet(
                "QListWidget { background: #1a1a2e; color: #e8e8f0; border: none; }"
                "QListWidget::item:selected { background: #2d2d5e; }"
            )
            for dev in devices:
                active_marker = " ●" if dev.get("is_active") else ""
                lst.addItem(f"{dev['name']}  ({dev['type']}){active_marker}")
            lst.setCurrentRow(0)
            dlg_layout.addWidget(lst)

            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel
            )
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            dlg_layout.addWidget(btns)

            if dlg.exec() == QDialog.DialogCode.Accepted:
                row = lst.currentRow()
                if 0 <= row < len(devices):
                    device_id = devices[row]["id"]
                    try:
                        self._sp.start_playback(
                            device_id=device_id, uris=[uri]
                        )
                    except Exception as exc2:
                        QMessageBox.warning(self, "Playback Error", str(exc2))
        else:
            # No devices at all — offer to open the web player
            from PySide6.QtWidgets import QDialog, QDialogButtonBox
            dlg = QDialog(self)
            dlg.setWindowTitle("No Spotify Device Found")
            dlg.setMinimumWidth(340)
            dlg_layout = QVBoxLayout(dlg)

            msg_lbl = QLabel(
                "No active Spotify device was found.\n\n"
                "To play through Spotify Connect you need at least one\n"
                "active device — desktop app, mobile app, or web player.\n\n"
                "Click Open Web Player to launch Spotify in your browser,\n"
                "then double-click the track again."
            )
            msg_lbl.setWordWrap(True)
            msg_lbl.setStyleSheet("color: #9090b0; font-size: 13px;")
            dlg_layout.addWidget(msg_lbl)

            btns = QDialogButtonBox()
            open_btn   = btns.addButton("Open Web Player",
                                        QDialogButtonBox.ButtonRole.ActionRole)
            cancel_btn = btns.addButton("Cancel",           # noqa: F841
                                        QDialogButtonBox.ButtonRole.RejectRole)
            open_btn.clicked.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl("https://open.spotify.com")
                )
            )
            btns.rejected.connect(dlg.reject)
            dlg_layout.addWidget(btns)
            dlg.exec()

    # ── Transport controls ────────────────────────────────────────────

    def _set_transport_enabled(self, enabled: bool) -> None:
        for btn in (self._prev_btn, self._playpause_btn,
                    self._next_btn, self._stop_btn):
            btn.setEnabled(enabled)

    def _update_playpause_icon(self) -> None:
        self._playpause_btn.setText("⏸" if self._is_playing else "▶")

    @Slot()
    def _on_playpause(self) -> None:
        if not self._sp:
            return
        try:
            if self._is_playing:
                self._sp.pause_playback()
                self._is_playing = False
            else:
                self._sp.start_playback()   # resume whatever was last playing
                self._is_playing = True
            self._update_playpause_icon()
        except spotipy.SpotifyException as exc:
            if exc.http_status in (404, 403):
                self._handle_no_device("")
            else:
                QMessageBox.warning(self, "Playback Error", str(exc))

    @Slot()
    def _on_prev(self) -> None:
        if not self._sp:
            return
        try:
            self._sp.previous_track()
            self._is_playing = True
            self._update_playpause_icon()
            QTimer.singleShot(800, self._poll_playback)  # refresh label quickly
        except Exception as exc:
            QMessageBox.warning(self, "Playback Error", str(exc))

    @Slot()
    def _on_next(self) -> None:
        if not self._sp:
            return
        try:
            self._sp.next_track()
            self._is_playing = True
            self._update_playpause_icon()
            QTimer.singleShot(800, self._poll_playback)
        except Exception as exc:
            QMessageBox.warning(self, "Playback Error", str(exc))

    @Slot()
    def _on_stop(self) -> None:
        """Pause playback and seek back to the start of the track."""
        if not self._sp:
            return
        try:
            self._sp.pause_playback()
            self._sp.seek_track(0)
            self._is_playing = False
            self._update_playpause_icon()
            self._now_playing_lbl.setText("Stopped")
        except Exception as exc:
            QMessageBox.warning(self, "Playback Error", str(exc))

    @Slot()
    def _poll_playback(self) -> None:
        """Fetch current playback state and update the transport bar."""
        if not self._sp:
            return
        try:
            state = self._sp.current_playback()
        except Exception:
            return
        if not state:
            self._is_playing = False
            self._now_playing_lbl.setText("Nothing playing")
            self._set_transport_enabled(False)
            self._update_playpause_icon()
            return

        self._set_transport_enabled(True)
        self._is_playing = state.get("is_playing", False)
        self._update_playpause_icon()

        item = state.get("item")
        if item:
            title   = item.get("name", "")
            artists = ", ".join(a["name"] for a in item.get("artists", []))
            device  = (state.get("device") or {}).get("name", "")
            label   = f"♫  {title}  —  {artists}"
            if device:
                label += f"  ·  {device}"
            # Truncate so it fits without wrapping
            if len(label) > 80:
                label = label[:77] + "…"
            self._now_playing_lbl.setText(label)
        else:
            self._now_playing_lbl.setText("Nothing playing")

    @Slot()
    def _open_dev_docs(self) -> None:
        QDesktopServices.openUrl(
            QUrl("https://developer.spotify.com/dashboard/create")
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ms_to_mmss(ms: int) -> str:
    s   = ms // 1000
    m   = s  //  60
    sec = s  %   60
    return f"{m}:{sec:02d}"

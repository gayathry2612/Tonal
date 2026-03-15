"""
Main application window.

Wires the Library, Player, AlarmManager, LibraryPanel, TrackListView,
PlayerControls, SpotifyPanel, and YouTubePanel together via Qt signals/slots.

Layout
------
Toolbar (search + alarm button)
QTabWidget
  ├── Tab 0 "Local Music"   ← original splitter + animated background
  ├── Tab 1 "Spotify"       ← SpotifyPanel
  └── Tab 2 "YouTube Music" ← YouTubePanel
PlayerControls (fixed bottom bar)
StatusBar
"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QStatusBar, QLineEdit, QLabel, QToolBar,
    QTabWidget, QMessageBox, QPushButton, QSystemTrayIcon, QMenu, QApplication,
)
from PySide6.QtCore import Qt, Slot, QSettings, QSize, QTimer, QEvent, QUrl
from PySide6.QtGui import QAction, QFont, QIcon, QPixmap, QPainter, QColor, QPen, QBrush
from PySide6.QtMultimedia import QMediaPlayer

from tonal.core.player         import Player
from tonal.core.library        import Library
from tonal.core.alarm_manager  import AlarmManager
from tonal.ui.library_panel    import LibraryPanel
from tonal.ui.track_list       import TrackListView
from tonal.ui.player_controls  import PlayerControls
from tonal.ui.animated_background import AnimatedBackground
from tonal.ui.spotify_panel    import SpotifyPanel
from tonal.ui.youtube_panel    import YouTubePanel
from tonal.ui.alarm_dialog     import AlarmDialog


def _app_data_dir() -> Path:
    """Return platform-appropriate app data directory."""
    return Path.home() / ".tonal"


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tonal")
        self.setMinimumSize(900, 580)

        # ── Data layer ───────────────────────────────────────────────
        data_dir = _app_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)

        self._library       = Library(str(data_dir / "library.db"), parent=self)
        self._player        = Player(parent=self)
        self._alarm_manager = AlarmManager(data_dir, parent=self)
        self._settings      = QSettings("Tonal", "Tonal")

        # ── Build UI ─────────────────────────────────────────────────
        self._build_ui()
        self._connect_signals()

        # ── System tray (background alarm mode) ──────────────────────
        self._quit_requested = False
        self._setup_tray()

        # ── Restore saved state ──────────────────────────────────────
        self._restore_geometry()
        self._load_initial_data()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._build_toolbar())

        # ── Tab widget ────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setObjectName("mainTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)

        # Tab 0: Local Music (original layout)
        self._local_content = self._build_local_tab()
        self._tabs.addTab(self._local_content, "  ♫  Local Music  ")

        # Tab 1: Spotify
        self._spotify_panel = SpotifyPanel(data_dir=_app_data_dir())
        self._tabs.addTab(self._spotify_panel, "    Spotify  ")

        # Tab 2: YouTube Music
        self._youtube_panel = YouTubePanel()
        self._tabs.addTab(self._youtube_panel, "  ▶  YouTube Music  ")

        root.addWidget(self._tabs, 1)

        # ── Player bar ───────────────────────────────────────────────
        self._player_controls = PlayerControls()
        root.addWidget(self._player_controls)

        # ── Status bar ───────────────────────────────────────────────
        self._status = QStatusBar()
        self._status.setObjectName("statusBar")
        self.setStatusBar(self._status)
        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("statusLabel")
        self._status.addWidget(self._status_label)

    def _build_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Search")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet(
            "QToolBar { background: #0f0f1e; border-bottom: 1px solid #2d2d4e;"
            " padding: 4px 8px; }"
        )
        toolbar.setIconSize(QSize(16, 16))

        spacer_left = QWidget()
        spacer_left.setFixedWidth(4)
        toolbar.addWidget(spacer_left)

        self._global_search = QLineEdit()
        self._global_search.setPlaceholderText("Search library…")
        self._global_search.setFixedWidth(260)
        self._global_search.setClearButtonEnabled(True)
        toolbar.addWidget(self._global_search)

        # Spacer pushes alarm button to the right
        spacer_mid = QWidget()
        spacer_mid.setSizePolicy(
            spacer_mid.sizePolicy().horizontalPolicy(),
            spacer_mid.sizePolicy().verticalPolicy(),
        )
        from PySide6.QtWidgets import QSizePolicy as QSP
        spacer_mid.setSizePolicy(QSP.Policy.Expanding, QSP.Policy.Preferred)
        toolbar.addWidget(spacer_mid)

        # Alarm button
        self._alarm_btn = QPushButton("⏰")
        self._alarm_btn.setToolTip("Alarms")
        self._alarm_btn.setFixedSize(36, 36)
        self._alarm_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9090b0; border: none;"
            " font-size: 18px; border-radius: 6px; }"
            "QPushButton:hover { background: #2d2d4e; color: #e8e8f0; }"
            "QPushButton:pressed { background: #3d3d6e; }"
        )
        self._alarm_btn.clicked.connect(self._on_alarm_btn)
        toolbar.addWidget(self._alarm_btn)

        spacer_right = QWidget()
        spacer_right.setFixedWidth(4)
        toolbar.addWidget(spacer_right)

        return toolbar

    def _build_local_tab(self) -> QWidget:
        """Build the Local Music tab widget with animated background + splitter."""
        content = QWidget()
        content.setAutoFillBackground(False)
        self._local_content_ref = content   # keep for eventFilter

        # Animated background — absolute positioned sibling of splitter
        self._bg = AnimatedBackground(content)
        self._bg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._bg.lower()

        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setAutoFillBackground(False)

        self._library_panel = LibraryPanel()
        self._track_list    = TrackListView()

        self._splitter.addWidget(self._library_panel)
        self._splitter.addWidget(self._track_list)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([190, 660])

        content_layout.addWidget(self._splitter)
        content.installEventFilter(self)

        return content

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Library panel → MainWindow
        self._library_panel.view_changed.connect(self._on_view_changed)
        self._library_panel.artist_selected.connect(self._on_artist_selected)
        self._library_panel.album_selected.connect(self._on_album_selected)
        self._library_panel.folder_scan_requested.connect(self._on_scan_requested)
        self._library_panel.folder_remove_requested.connect(self._on_folder_remove)

        # Track list → Player
        self._track_list.play_requested.connect(self._on_play_requested)

        # Player → UI
        self._player.track_changed.connect(self._player_controls.set_track)
        self._player.state_changed.connect(self._player_controls.set_state)
        self._player.position_changed.connect(self._player_controls.set_position)
        self._player.duration_changed.connect(self._player_controls.set_duration)
        self._player.track_changed.connect(self._on_track_changed)
        self._player.queue_ended.connect(self._on_queue_ended)
        self._player.error_occurred.connect(self._on_player_error)

        # Player controls → Player
        self._player_controls.play_pause_clicked.connect(self._player.toggle_play_pause)
        self._player_controls.next_clicked.connect(self._player.next_track)
        self._player_controls.prev_clicked.connect(self._player.prev_track)
        self._player_controls.skip_fwd_clicked.connect(
            lambda: self._player.skip_forward(10)
        )
        self._player_controls.skip_bwd_clicked.connect(
            lambda: self._player.skip_backward(10)
        )
        self._player_controls.seek_requested.connect(self._player.seek)
        self._player_controls.volume_changed.connect(self._player.set_volume)
        self._player_controls.shuffle_toggled.connect(self._player.set_shuffle)
        self._player_controls.repeat_cycled.connect(self._on_repeat_cycled)

        # Library scanning feedback
        self._library.scan_progress.connect(self._on_scan_progress)
        self._library.scan_finished.connect(self._on_scan_finished)
        self._library.scan_error.connect(self._on_scan_error)

        # Global search (only affects local music tab)
        self._global_search.textChanged.connect(self._on_global_search)

        # YouTube playback
        self._youtube_panel.play_requested.connect(self._on_youtube_play)

        # Alarm triggers
        self._alarm_manager.alarm_triggered.connect(self._on_alarm_triggered)

        # Alarm indicator: flash the toolbar button while alarm plays
        self._alarm_manager.alarm_triggered.connect(
            lambda _: self._alarm_btn.setStyleSheet(
                "QPushButton { background: #7c6af7; color: white; border: none;"
                " font-size: 18px; border-radius: 6px; }"
            )
        )

    # ------------------------------------------------------------------
    # Data initialisation
    # ------------------------------------------------------------------

    def _load_initial_data(self) -> None:
        tracks  = self._library.get_all_tracks()
        self._track_list.set_tracks(tracks)
        folders = self._library.get_folders()
        self._library_panel.set_folders(folders)
        count = len(tracks)
        self._set_status(f"{count} track{'s' if count != 1 else ''} in library")

    # ------------------------------------------------------------------
    # Slots: library panel navigation
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_view_changed(self, view: str) -> None:
        self._global_search.clear()
        if view == "songs":
            self._track_list.set_tracks(self._library.get_all_tracks())
        elif view == "artists":
            self._library_panel.set_artists(self._library.get_artists())
            self._track_list.set_tracks(self._library.get_all_tracks())
        elif view == "albums":
            self._library_panel.set_albums(self._library.get_albums())
            self._track_list.set_tracks(self._library.get_all_tracks())

    @Slot(str)
    def _on_artist_selected(self, artist: str) -> None:
        tracks = self._library.get_tracks_by_artist(artist)
        self._track_list.set_tracks(tracks)
        self._set_status(f"{len(tracks)} track{'s' if len(tracks) != 1 else ''} by {artist}")

    @Slot(str)
    def _on_album_selected(self, album: str) -> None:
        tracks = self._library.get_tracks_by_album(album)
        self._track_list.set_tracks(tracks)
        plural = "s" if len(tracks) != 1 else ""
        self._set_status(f'{len(tracks)} track{plural} in \u201c{album}\u201d')

    # ------------------------------------------------------------------
    # Slots: folder management
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_scan_requested(self, folder: str) -> None:
        self._set_status(f"Scanning {folder}…")
        self._library.scan_folder(folder)

    @Slot(str, int)
    def _on_scan_progress(self, path: str, count: int) -> None:
        self._set_status(f"Scanning… {count} tracks found  ({os.path.basename(path)})")

    @Slot(int)
    def _on_scan_finished(self, count: int) -> None:
        self._set_status(f"Scan complete — added {count} track{'s' if count != 1 else ''}")
        self._load_initial_data()

    @Slot(str)
    def _on_scan_error(self, msg: str) -> None:
        self._set_status(f"Scan error: {msg}")
        QMessageBox.warning(self, "Scan Error", msg)

    @Slot(str)
    def _on_folder_remove(self, folder: str) -> None:
        self._library.remove_folder(folder)
        self._load_initial_data()
        self._set_status(f"Removed folder: {folder}")

    # ------------------------------------------------------------------
    # Slots: local playback
    # ------------------------------------------------------------------

    @Slot(list, int)
    def _on_play_requested(self, tracks: list, index: int) -> None:
        if tracks:
            self._player.load_queue(tracks, start_index=index)

    @Slot(dict)
    def _on_track_changed(self, track: dict) -> None:
        title  = track.get("title") or "Unknown"
        artist = track.get("artist") or ""
        label  = f"▶  {title}"
        if artist:
            label += f"  —  {artist}"
        self.setWindowTitle(f"{label}  ·  Tonal")
        self._track_list.highlight_playing(track.get("path", ""))

    @Slot()
    def _on_queue_ended(self) -> None:
        self.setWindowTitle("Tonal")
        self._set_status("Playback finished")

    @Slot(str)
    def _on_player_error(self, msg: str) -> None:
        self._set_status(msg)

    @Slot()
    def _on_repeat_cycled(self) -> None:
        mode = self._player.cycle_repeat()
        self._player_controls.set_repeat_label(mode)

    # ------------------------------------------------------------------
    # Slots: YouTube playback
    # ------------------------------------------------------------------

    @Slot(str, dict)
    def _on_youtube_play(self, stream_url: str, track: dict) -> None:
        """Load a YouTube stream URL directly into the media player."""
        synthetic = {
            "path":   stream_url,          # reused as the media URL
            "title":  track.get("title",  "YouTube Track"),
            "artist": track.get("artist", ""),
            "album":  "",
            "duration": 0,
        }
        # Override load_queue to use a URL source
        from PySide6.QtCore import QUrl as _QUrl
        self._player._queue         = [synthetic]
        self._player._play_order    = [0]
        self._player._order_pos     = 0
        self._player._autoplay      = True
        self._player._media.setSource(_QUrl(stream_url))
        self._player.track_changed.emit(synthetic)
        # status
        title  = track.get("title", "")
        artist = track.get("artist", "")
        self._set_status(f"▶  {title}  —  {artist}" if artist else f"▶  {title}")

    # ------------------------------------------------------------------
    # Slots: global search
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_global_search(self, text: str) -> None:
        if text.strip():
            tracks = self._library.search(text.strip())
        else:
            tracks = self._library.get_all_tracks()
        self._track_list.set_tracks(tracks)
        if text.strip():
            plural = "s" if len(tracks) != 1 else ""
            self._set_status(f'{len(tracks)} result{plural} for \u201c{text}\u201d')

    # ------------------------------------------------------------------
    # Slots: alarm
    # ------------------------------------------------------------------

    @Slot()
    def _on_alarm_btn(self) -> None:
        """Open the alarm manager dialog."""
        # Reset the alarm indicator style
        self._alarm_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9090b0; border: none;"
            " font-size: 18px; border-radius: 6px; }"
            "QPushButton:hover { background: #2d2d4e; color: #e8e8f0; }"
        )

        # Build search proxies for Spotify/YouTube alarm song selection
        spotify_fn = None
        if self._spotify_panel._sp is not None:
            def spotify_fn(q: str) -> list:
                return self._spotify_panel.search(q)

        youtube_fn = None
        try:
            from ytmusicapi import YTMusic as _YTM  # noqa: F401
            from tonal.ui.youtube_panel import _YTDLP_OK
            if _YTDLP_OK:
                def youtube_fn(q: str) -> list:
                    return self._youtube_panel.search(q)
        except ImportError:
            pass

        dlg = AlarmDialog(
            alarm_manager    = self._alarm_manager,
            library_tracks   = self._library.get_all_tracks(),
            spotify_search_fn = spotify_fn,
            youtube_search_fn = youtube_fn,
            parent           = self,
        )
        dlg.exec()

    @Slot(dict)
    def _on_alarm_triggered(self, track: dict) -> None:
        """Handle an alarm firing — show the window and play the selected track."""
        # Always bring the app to the foreground when an alarm fires
        self._show_window()

        source = track.get("source", "local")

        if source == "local":
            path = track.get("path", "")
            if path:
                self._player.load_queue([track], start_index=0)
                # Belt-and-suspenders: if the platform's backend delivers
                # BufferedMedia before LoadedMedia (or neither), kick play()
                # explicitly once the event loop has processed the setSource.
                QTimer.singleShot(300, self._player.play)
                self._set_status(
                    f"⏰  Alarm  —  {track.get('title', '')}  by  {track.get('artist', '')}"
                )

        elif source == "spotify":
            if self._spotify_panel._sp:
                try:
                    self._spotify_panel._sp.start_playback(
                        uris=[track["spotify_uri"]]
                    )
                    self._set_status(
                        f"⏰  Alarm (Spotify)  —  {track.get('title', '')}"
                    )
                    self._tabs.setCurrentIndex(1)
                except Exception as e:
                    self._set_status(f"Alarm Spotify error: {e}")
            else:
                self._set_status("⏰  Alarm triggered — Spotify not connected")

        elif source == "youtube":
            video_id = track.get("video_id", "")
            if video_id:
                self._set_status(f"⏰  Alarm — loading  {track.get('title', '')}…")
                self._tabs.setCurrentIndex(2)
                self._youtube_panel._on_stream_ready_from_alarm(video_id, track)

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self) -> None:
        """Create the system-tray icon that keeps Tonal alive in background."""
        self._tray = QSystemTrayIcon(self._make_tray_icon(), self)
        self._tray.setToolTip("Tonal")

        menu = QMenu()

        open_action = menu.addAction("Open Tonal")
        open_action.triggered.connect(self._show_window)

        menu.addSeparator()

        self._tray_alarm_action = menu.addAction("No active alarms")
        self._tray_alarm_action.setEnabled(False)

        menu.addSeparator()

        quit_action = menu.addAction("Quit Tonal")
        quit_action.triggered.connect(self._quit_app)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)

        # Update the alarm count label whenever alarms change
        self._alarm_manager.alarms_changed.connect(self._update_tray_label)
        self._update_tray_label()

        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.show()

    def _make_tray_icon(self) -> QIcon:
        """Return the app icon, or a programmatic fallback."""
        candidates = [
            Path(__file__).parent.parent.parent.parent / "assets" / "icons" / "tonal.png",
        ]
        for p in candidates:
            if p.exists():
                return QIcon(str(p))

        # Programmatic purple circle with a music note
        px = QPixmap(32, 32)
        px.fill(Qt.GlobalColor.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor("#7c6af7")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(1, 1, 30, 30)
        pen = QPen(QColor("white"))
        pen.setWidth(2)
        painter.setPen(pen)
        # note head
        painter.setBrush(QBrush(QColor("white")))
        painter.drawEllipse(7, 20, 7, 6)
        # note stem
        painter.drawLine(14, 23, 14, 9)
        # flag / beam
        painter.drawLine(14, 9, 22, 7)
        painter.drawLine(22, 7, 22, 17)
        painter.end()
        return QIcon(px)

    @Slot()
    def _update_tray_label(self) -> None:
        alarms = [a for a in self._alarm_manager.get_alarms() if a.get("enabled")]
        n = len(alarms)
        if n == 0:
            self._tray_alarm_action.setText("No active alarms")
        else:
            self._tray_alarm_action.setText(f"{n} active alarm{'s' if n != 1 else ''}")

    @Slot()
    def _show_window(self) -> None:
        """Restore the window from tray."""
        self.show()
        self.raise_()
        self.activateWindow()

    @Slot()
    def _quit_app(self) -> None:
        """Truly quit — called from tray 'Quit' action."""
        self._quit_requested = True
        self._tray.hide()
        QApplication.quit()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj is self._local_content_ref and event.type() == QEvent.Type.Resize:
            self._bg.setGeometry(self._local_content_ref.rect())
        return super().eventFilter(obj, event)

    def _restore_geometry(self) -> None:
        geom = self._settings.value("window/geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1100, 700)
            self._centre_on_screen()

        splitter_state = self._settings.value("window/splitter")
        if splitter_state:
            self._splitter.restoreState(splitter_state)

        vol = self._settings.value("player/volume", 0.7, type=float)
        self._player.set_volume(vol)
        self._player_controls._volume_slider.setValue(int(vol * 100))

        tab_idx = self._settings.value("window/tab", 0, type=int)
        self._tabs.setCurrentIndex(tab_idx)

    def _centre_on_screen(self) -> None:
        screen = self.screen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                (geo.width()  - self.width())  // 2,
                (geo.height() - self.height()) // 2,
            )

    def closeEvent(self, event) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/splitter", self._splitter.saveState())
        self._settings.setValue("player/volume",   self._player.volume())
        self._settings.setValue("window/tab",       self._tabs.currentIndex())

        # If the user clicked the OS quit (not our tray "Quit Tonal"), check
        # whether we should stay alive in the background for pending alarms.
        if not self._quit_requested and QSystemTrayIcon.isSystemTrayAvailable():
            active = [a for a in self._alarm_manager.get_alarms() if a.get("enabled")]
            if active:
                event.ignore()
                self.hide()
                n = len(active)
                self._tray.showMessage(
                    "Tonal",
                    f"Running in background — {n} alarm{'s' if n != 1 else ''} active.\n"
                    "Double-click the tray icon to reopen.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
                return

        self._tray.hide()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        self._status_label.setText(msg)

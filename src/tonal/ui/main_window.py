"""
Main application window.

Wires the Library, Player, LibraryPanel, TrackListView,
and PlayerControls together via Qt signals/slots.
"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QStatusBar, QLineEdit, QLabel, QToolBar,
    QMessageBox,
)
from PySide6.QtCore import Qt, Slot, QSettings, QSize, QTimer, QEvent
from PySide6.QtGui import QAction, QFont

from tonal.core.player  import Player
from tonal.core.library import Library
from tonal.ui.library_panel        import LibraryPanel
from tonal.ui.track_list           import TrackListView
from tonal.ui.player_controls      import PlayerControls
from tonal.ui.animated_background  import AnimatedBackground


def _app_data_dir() -> Path:
    """Return platform-appropriate app data directory."""
    home = Path.home()
    return home / ".tonal"


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tonal")
        self.setMinimumSize(860, 560)

        # ── Data layer ───────────────────────────────────────────────
        data_dir = _app_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(data_dir / "library.db")

        self._library = Library(db_path, parent=self)
        self._player  = Player(parent=self)
        self._settings = QSettings("Tonal", "Tonal")

        # ── Build UI ─────────────────────────────────────────────────
        self._build_ui()
        self._connect_signals()

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

        # Global search bar in a top toolbar
        toolbar = QToolBar("Search")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet(
            "QToolBar { background: #0f0f1e; border-bottom: 1px solid #2d2d4e; padding: 4px 8px; }"
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

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        # ── Main content area ────────────────────────────────────────
        # Plain container widget — the animated background is a *sibling*
        # of the splitter (not its parent), so Qt never skips its paintEvent.
        content = QWidget()
        content.setAutoFillBackground(False)
        self._content = content

        # Space animation layer — fills content, no layout, sits behind splitter
        self._bg = AnimatedBackground(content)
        self._bg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._bg.lower()  # z-order: below the splitter

        # Splitter with panels on top (panels have rgba backgrounds → animation shows through)
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
        root.addWidget(content, 1)

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

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Library panel → MainWindow actions
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

        # Global search
        self._global_search.textChanged.connect(self._on_global_search)

    # ------------------------------------------------------------------
    # Data initialisation
    # ------------------------------------------------------------------

    def _load_initial_data(self) -> None:
        """Load all tracks from DB and refresh the library panel."""
        tracks = self._library.get_all_tracks()
        self._track_list.set_tracks(tracks)

        folders = self._library.get_folders()
        self._library_panel.set_folders(folders)

        self._status_label.setText(
            f"{len(tracks)} track{'s' if len(tracks) != 1 else ''} in library"
        )

    # ------------------------------------------------------------------
    # Slots: library panel navigation
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_view_changed(self, view: str) -> None:
        self._global_search.clear()
        if view == "songs":
            tracks = self._library.get_all_tracks()
            self._track_list.set_tracks(tracks)
        elif view == "artists":
            artists = self._library.get_artists()
            self._library_panel.set_artists(artists)
            # Show all tracks until an artist is selected
            tracks = self._library.get_all_tracks()
            self._track_list.set_tracks(tracks)
        elif view == "albums":
            albums = self._library.get_albums()
            self._library_panel.set_albums(albums)
            tracks = self._library.get_all_tracks()
            self._track_list.set_tracks(tracks)

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

    @Slot(str)
    def _on_scan_progress(self, path: str, count: int) -> None:
        fname = os.path.basename(path)
        self._set_status(f"Scanning… {count} tracks found  ({fname})")

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
    # Slots: playback
    # ------------------------------------------------------------------

    @Slot(list, int)
    def _on_play_requested(self, tracks: list, index: int) -> None:
        if not tracks:
            return
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
    # Geometry persistence
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj is self._content and event.type() == QEvent.Type.Resize:
            self._bg.setGeometry(self._content.rect())
        return super().eventFilter(obj, event)

    def _restore_geometry(self) -> None:
        geom = self._settings.value("window/geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1024, 680)
            self._centre_on_screen()

        splitter_state = self._settings.value("window/splitter")
        if splitter_state:
            self._splitter.restoreState(splitter_state)

        vol = self._settings.value("player/volume", 0.7, type=float)
        self._player.set_volume(vol)
        self._player_controls._volume_slider.setValue(int(vol * 100))

    def _centre_on_screen(self) -> None:
        from PySide6.QtGui import QScreen
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
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        self._status_label.setText(msg)

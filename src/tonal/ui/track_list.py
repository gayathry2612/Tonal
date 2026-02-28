"""
Centre panel: a sortable, searchable QTableWidget listing tracks.

Emits play_requested(list[dict], int) when the user double-clicks a row.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMenu, QLabel, QLineEdit, QPushButton,
)
from PySide6.QtCore import Qt, Signal, Slot, QPoint
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut

from tonal.core.library import format_duration


# Column indices
COL_NUM    = 0
COL_TITLE  = 1
COL_ARTIST = 2
COL_ALBUM  = 3
COL_DUR    = 4

_COLUMNS = ["#", "Title", "Artist", "Album", "Duration"]

_ACCENT          = QColor("#7c6af7")
_PLAYING_BG      = QColor("#2a2a4a")
_PLAYING_TEXT    = QColor("#c8bcff")


class TrackListView(QWidget):
    """
    Signals
    -------
    play_requested(list[dict], int)
        Emitted on double-click.  Passes the *full current filtered list*
        as the queue and the clicked row index.
    queue_track(dict)
        Emitted via context menu "Add to queue" action (not yet wired
        to the player – extend as needed).
    """

    play_requested = Signal(list, int)
    queue_track    = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: list[dict] = []          # all tracks for current view
        self._filtered: list[dict] = []        # after search filter
        self._playing_path: str = ""
        # Let the animated background paint through the container
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top search / filter bar ──────────────────────────────────
        top_bar = QWidget()
        top_bar.setStyleSheet("background-color: rgba(22, 33, 62, 200); border-bottom: 1px solid rgba(60, 60, 100, 160);")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 6, 12, 6)
        top_layout.setSpacing(8)

        self._count_label = QLabel("0 tracks")
        self._count_label.setObjectName("statusLabel")

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter tracks…")
        self._search_box.setFixedWidth(200)
        self._search_box.setClearButtonEnabled(True)

        top_layout.addWidget(self._count_label)
        top_layout.addStretch(1)
        top_layout.addWidget(self._search_box)

        layout.addWidget(top_bar)

        # ── Track table ──────────────────────────────────────────────
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(True)
        self._table.setShowGrid(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_NUM,    QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_TITLE,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_ARTIST, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_ALBUM,  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_DUR,    QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_NUM, 40)
        self._table.setColumnWidth(COL_DUR, 60)
        self._table.verticalHeader().setDefaultSectionSize(34)

        layout.addWidget(self._table, 1)

        # Wire
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._search_box.textChanged.connect(self._on_search)

        # Keyboard shortcut: Enter / Return = play selected row
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self._table)
        shortcut.activated.connect(self._play_selected)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @Slot(list)
    def set_tracks(self, tracks: list[dict]) -> None:
        """Populate with a new list of track dicts."""
        self._tracks   = tracks
        self._filtered = list(tracks)
        # Reapply any active search
        q = self._search_box.text().strip().lower()
        if q:
            self._filtered = [
                t for t in tracks
                if q in (t.get("title") or "").lower()
                or q in (t.get("artist") or "").lower()
                or q in (t.get("album") or "").lower()
            ]
        self._repopulate()

    @Slot(str)
    def highlight_playing(self, path: str) -> None:
        """Visually mark the row whose path matches *path* as currently playing."""
        self._playing_path = path
        for row in range(self._table.rowCount()):
            is_playing = self._row_track(row).get("path") == path
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is None:
                    continue
                if is_playing:
                    item.setBackground(_PLAYING_BG)
                    item.setForeground(_PLAYING_TEXT)
                    bold = QFont()
                    bold.setBold(True)
                    item.setFont(bold)
                else:
                    item.setBackground(QColor(0, 0, 0, 0))
                    item.setForeground(QColor("#9090b0"))
                    item.setFont(QFont())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _repopulate(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for i, track in enumerate(self._filtered):
            self._table.insertRow(i)

            track_num = track.get("track_number") or ""
            num_item  = _item(str(track_num) if track_num else "")
            num_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            num_item.setData(Qt.ItemDataRole.UserRole, i)  # store filtered index

            self._table.setItem(i, COL_NUM,    num_item)
            self._table.setItem(i, COL_TITLE,  _item(track.get("title")  or ""))
            self._table.setItem(i, COL_ARTIST, _item(track.get("artist") or ""))
            self._table.setItem(i, COL_ALBUM,  _item(track.get("album")  or ""))

            dur = track.get("duration") or 0
            dur_item = _item(format_duration(dur))
            dur_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(i, COL_DUR, dur_item)

            # Highlight if currently playing
            if track.get("path") == self._playing_path:
                for col in range(self._table.columnCount()):
                    it = self._table.item(i, col)
                    if it:
                        it.setBackground(_PLAYING_BG)
                        it.setForeground(_PLAYING_TEXT)
                        bold = QFont()
                        bold.setBold(True)
                        it.setFont(bold)

        self._table.setSortingEnabled(True)
        count = len(self._filtered)
        self._count_label.setText(
            f"{count} track{'s' if count != 1 else ''}"
        )

    def _row_track(self, row: int) -> dict:
        """Return the track dict for a given visible row."""
        idx_item = self._table.item(row, COL_NUM)
        if idx_item is not None:
            idx = idx_item.data(Qt.ItemDataRole.UserRole)
            if idx is not None and 0 <= idx < len(self._filtered):
                return self._filtered[idx]
        # Fallback: try to match by title
        title = (self._table.item(row, COL_TITLE) or _item("")).text()
        for t in self._filtered:
            if t.get("title") == title:
                return t
        return {}

    def _visible_tracks(self) -> list[dict]:
        """Return track dicts in the current visual (sorted) row order."""
        result = []
        for row in range(self._table.rowCount()):
            t = self._row_track(row)
            if t:
                result.append(t)
        return result

    @Slot(int, int)
    def _on_double_click(self, row: int, _col: int) -> None:
        tracks = self._visible_tracks()
        if 0 <= row < len(tracks):
            self.play_requested.emit(tracks, row)

    @Slot()
    def _play_selected(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if rows:
            tracks = self._visible_tracks()
            idx = rows[0].row()
            if 0 <= idx < len(tracks):
                self.play_requested.emit(tracks, idx)

    @Slot(QPoint)
    def _on_context_menu(self, pos: QPoint) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        track = self._row_track(row)
        if not track:
            return

        menu = QMenu(self)
        act_play  = menu.addAction("▶  Play Now")
        act_queue = menu.addAction("  Add to Queue")
        menu.addSeparator()
        act_info  = menu.addAction("ℹ  Track Info")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen == act_play:
            tracks = self._visible_tracks()
            if 0 <= row < len(tracks):
                self.play_requested.emit(tracks, row)
        elif chosen == act_queue:
            self.queue_track.emit(track)
        elif chosen == act_info:
            _show_info(track, self)

    @Slot(str)
    def _on_search(self, text: str) -> None:
        q = text.strip().lower()
        if q:
            self._filtered = [
                t for t in self._tracks
                if q in (t.get("title") or "").lower()
                or q in (t.get("artist") or "").lower()
                or q in (t.get("album") or "").lower()
            ]
        else:
            self._filtered = list(self._tracks)
        self._repopulate()


def _item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setForeground(QColor("#9090b0"))
    return item


def _show_info(track: dict, parent: QWidget) -> None:
    from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
    dlg = QDialog(parent)
    dlg.setWindowTitle("Track Info")
    dlg.setMinimumWidth(360)
    layout = QFormLayout(dlg)
    fields = [
        ("Title",    track.get("title")),
        ("Artist",   track.get("artist")),
        ("Album",    track.get("album")),
        ("Year",     track.get("year")),
        ("Genre",    track.get("genre")),
        ("Duration", format_duration(track.get("duration") or 0)),
        ("Track #",  track.get("track_number")),
        ("Path",     track.get("path")),
    ]
    for label, value in fields:
        lbl = QLabel(str(value) if value is not None else "—")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addRow(f"<b>{label}</b>", lbl)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    buttons.accepted.connect(dlg.accept)
    layout.addRow(buttons)
    dlg.exec()

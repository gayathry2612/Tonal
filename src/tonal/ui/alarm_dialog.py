"""
Alarm manager dialog.

Opens from the toolbar alarm button.  Lets the user:
  • See all configured alarms with enable/disable toggles
  • Add new alarms (time, repeat days, song source + track)
  • Remove alarms

Song selection tabs inside AddAlarmDialog:
  Local    – searchable list from the local library
  Spotify  – pass a SpotifySearchProxy so the dialog can reuse auth
  YouTube  – simple search field (no auth needed)
"""
from __future__ import annotations

import uuid
from typing import Callable

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame,
    QTimeEdit, QCheckBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTabWidget, QDialogButtonBox, QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTime, Slot, Signal
from PySide6.QtGui import QColor, QFont

from tonal.core.alarm_manager import AlarmManager, DAYS_SHORT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "font-size: 10px; font-weight: 700; color: #60607a;"
        "letter-spacing: 1px; padding: 6px 0 2px 0;"
    )
    return lbl


def _track_display(track: dict) -> str:
    title  = track.get("title")  or track.get("name")  or "Unknown"
    artist = track.get("artist") or ""
    return f"{title}  —  {artist}" if artist else title


# ---------------------------------------------------------------------------
# AlarmRow  (one row in the main alarm list)
# ---------------------------------------------------------------------------

class _AlarmRow(QFrame):
    toggle_requested = Signal(str, bool)   # (alarm_id, enabled)
    delete_requested = Signal(str)         # alarm_id

    def __init__(self, alarm: dict, parent=None):
        super().__init__(parent)
        self._alarm_id = alarm["id"]
        self.setObjectName("alarmRow")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "#alarmRow { background: rgba(22,33,62,200); border-radius: 8px;"
            " border: 1px solid #2d2d4e; margin: 2px 0; }"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(12)

        # Enable toggle
        self._chk = QCheckBox()
        self._chk.setChecked(alarm.get("enabled", True))
        self._chk.stateChanged.connect(
            lambda s: self.toggle_requested.emit(
                self._alarm_id, s == Qt.CheckState.Checked.value
            )
        )
        row.addWidget(self._chk)

        # Time label
        h = alarm.get("hour", 0)
        m = alarm.get("minute", 0)
        time_lbl = QLabel(f"{h:02d}:{m:02d}")
        time_lbl.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #e8e8f0; min-width: 60px;"
        )
        row.addWidget(time_lbl)

        # Details column
        detail_col = QVBoxLayout()
        detail_col.setSpacing(2)

        label = alarm.get("label") or _track_display(alarm.get("track_data", {}))
        name_lbl = QLabel(label or "No track selected")
        name_lbl.setStyleSheet("font-size: 13px; color: #c8bcff;")
        detail_col.addWidget(name_lbl)

        days = alarm.get("days", [])
        if days:
            days_str = ", ".join(d.capitalize() for d in days)
        else:
            days_str = "One-time"
        source = alarm.get("source", "local").capitalize()
        sub_lbl = QLabel(f"{days_str}  ·  {source}")
        sub_lbl.setStyleSheet("font-size: 11px; color: #60607a;")
        detail_col.addWidget(sub_lbl)

        row.addLayout(detail_col, 1)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #60607a; border: none;"
            " font-size: 14px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,80,80,120); color: #ff6060; }"
        )
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._alarm_id))
        row.addWidget(del_btn)


# ---------------------------------------------------------------------------
# Song selector (used inside AddAlarmDialog)
# ---------------------------------------------------------------------------

class _SongSelectorWidget(QWidget):
    """
    Three-tab widget to choose a song:
      Local | Spotify | YouTube

    Emits track_selected(dict) when the user double-clicks or confirms.
    """
    track_selected = Signal(dict)

    def __init__(
        self,
        library_tracks: list[dict],
        spotify_search_fn: Callable[[str], list[dict]] | None = None,
        youtube_search_fn: Callable[[str], list[dict]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._library_tracks = library_tracks
        self._spotify_fn     = spotify_search_fn
        self._youtube_fn     = youtube_search_fn
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tabs = QTabWidget()
        tabs.setObjectName("selectorTabs")

        # ── Local tab ─────────────────────────────────────────────────
        local_tab = QWidget()
        lt = QVBoxLayout(local_tab)
        lt.setContentsMargins(8, 8, 8, 8)
        lt.setSpacing(6)

        self._local_search = QLineEdit()
        self._local_search.setPlaceholderText("Filter local tracks…")
        self._local_search.setClearButtonEnabled(True)
        lt.addWidget(self._local_search)

        self._local_table = self._make_results_table()
        lt.addWidget(self._local_table)
        self._populate_local(self._library_tracks)

        self._local_search.textChanged.connect(self._on_local_search)
        self._local_table.cellDoubleClicked.connect(self._on_local_double_click)
        tabs.addTab(local_tab, "♫  Local")

        # ── Spotify tab ───────────────────────────────────────────────
        spotify_tab = QWidget()
        st = QVBoxLayout(spotify_tab)
        st.setContentsMargins(8, 8, 8, 8)
        st.setSpacing(6)

        if self._spotify_fn:
            sp_row = QHBoxLayout()
            self._spotify_search = QLineEdit()
            self._spotify_search.setPlaceholderText("Search Spotify…")
            self._spotify_search.setClearButtonEnabled(True)
            sp_btn = QPushButton("Search")
            sp_btn.setObjectName("btnSidebar")
            sp_row.addWidget(self._spotify_search, 1)
            sp_row.addWidget(sp_btn)
            st.addLayout(sp_row)

            self._spotify_table = self._make_results_table()
            st.addWidget(self._spotify_table)
            sp_btn.clicked.connect(self._on_spotify_search)
            self._spotify_search.returnPressed.connect(self._on_spotify_search)
            self._spotify_table.cellDoubleClicked.connect(self._on_spotify_double_click)
        else:
            no_auth = QLabel(
                "Spotify not connected.\nAuthenticate in the Spotify tab first."
            )
            no_auth.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_auth.setStyleSheet("color: #60607a; font-size: 13px;")
            st.addWidget(no_auth)

        tabs.addTab(spotify_tab, "  Spotify")

        # ── YouTube tab ───────────────────────────────────────────────
        yt_tab = QWidget()
        yt = QVBoxLayout(yt_tab)
        yt.setContentsMargins(8, 8, 8, 8)
        yt.setSpacing(6)

        if self._youtube_fn:
            yt_row = QHBoxLayout()
            self._yt_search = QLineEdit()
            self._yt_search.setPlaceholderText("Search YouTube Music…")
            self._yt_search.setClearButtonEnabled(True)
            yt_btn = QPushButton("Search")
            yt_btn.setObjectName("btnSidebar")
            yt_row.addWidget(self._yt_search, 1)
            yt_row.addWidget(yt_btn)
            yt.addLayout(yt_row)

            self._yt_table = self._make_results_table()
            yt.addWidget(self._yt_table)
            yt_btn.clicked.connect(self._on_youtube_search)
            self._yt_search.returnPressed.connect(self._on_youtube_search)
            self._yt_table.cellDoubleClicked.connect(self._on_youtube_double_click)
        else:
            no_yt = QLabel(
                "YouTube Music unavailable.\nInstall ytmusicapi and yt-dlp to enable."
            )
            no_yt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_yt.setStyleSheet("color: #60607a; font-size: 13px;")
            yt.addWidget(no_yt)

        tabs.addTab(yt_tab, "▶  YouTube")

        layout.addWidget(tabs)

    # ── Table factory ─────────────────────────────────────────────────

    def _make_results_table(self) -> QTableWidget:
        tbl = QTableWidget(0, 3)
        tbl.setHorizontalHeaderLabels(["Title", "Artist", "Duration"])
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        tbl.setColumnWidth(2, 60)
        tbl.verticalHeader().setDefaultSectionSize(30)
        tbl.setMinimumHeight(180)
        return tbl

    def _fill_table(self, tbl: QTableWidget, rows: list[tuple[str, str, str, dict]]) -> None:
        """rows = [(title, artist, duration, track_data), ...]"""
        tbl.setRowCount(0)
        for i, (title, artist, dur, data) in enumerate(rows):
            tbl.insertRow(i)
            for col, text in enumerate([title, artist, dur]):
                item = QTableWidgetItem(text)
                item.setForeground(QColor("#9090b0"))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, data)
                tbl.setItem(i, col, item)

    # ── Local ─────────────────────────────────────────────────────────

    def _populate_local(self, tracks: list[dict]) -> None:
        from tonal.core.library import format_duration
        rows = []
        for t in tracks:
            rows.append((
                t.get("title")  or "",
                t.get("artist") or "",
                format_duration(t.get("duration") or 0),
                {**t, "source": "local"},
            ))
        self._fill_table(self._local_table, rows)

    @Slot(str)
    def _on_local_search(self, text: str) -> None:
        q = text.strip().lower()
        if q:
            filtered = [
                t for t in self._library_tracks
                if q in (t.get("title")  or "").lower()
                or q in (t.get("artist") or "").lower()
                or q in (t.get("album")  or "").lower()
            ]
        else:
            filtered = self._library_tracks
        self._populate_local(filtered)

    @Slot(int, int)
    def _on_local_double_click(self, row: int, _col: int) -> None:
        item = self._local_table.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                self.track_selected.emit(data)

    # ── Spotify ───────────────────────────────────────────────────────

    @Slot()
    def _on_spotify_search(self) -> None:
        if not self._spotify_fn:
            return
        q = self._spotify_search.text().strip()
        if not q:
            return
        try:
            results = self._spotify_fn(q)
        except Exception as e:
            QMessageBox.warning(self, "Spotify Search", str(e))
            return
        rows = []
        for t in results:
            rows.append((
                t.get("title") or t.get("name") or "",
                t.get("artist") or "",
                t.get("duration") or "",
                t,
            ))
        self._fill_table(self._spotify_table, rows)

    @Slot(int, int)
    def _on_spotify_double_click(self, row: int, _col: int) -> None:
        item = self._spotify_table.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                self.track_selected.emit(data)

    # ── YouTube ───────────────────────────────────────────────────────

    @Slot()
    def _on_youtube_search(self) -> None:
        if not self._youtube_fn:
            return
        q = self._yt_search.text().strip()
        if not q:
            return
        try:
            results = self._youtube_fn(q)
        except Exception as e:
            QMessageBox.warning(self, "YouTube Search", str(e))
            return
        rows = []
        for t in results:
            rows.append((
                t.get("title") or "",
                t.get("artist") or "",
                t.get("duration") or "",
                t,
            ))
        self._fill_table(self._yt_table, rows)

    @Slot(int, int)
    def _on_youtube_double_click(self, row: int, _col: int) -> None:
        item = self._yt_table.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                self.track_selected.emit(data)


# ---------------------------------------------------------------------------
# Add / Edit Alarm Dialog
# ---------------------------------------------------------------------------

class AddAlarmDialog(QDialog):
    """Modal dialog to create or edit a single alarm."""

    def __init__(
        self,
        library_tracks: list[dict],
        spotify_search_fn=None,
        youtube_search_fn=None,
        existing: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Alarm" if existing else "Add Alarm")
        self.setMinimumSize(500, 540)
        self._existing   = existing
        self._track_data : dict = existing.get("track_data", {}) if existing else {}
        self._build_ui(library_tracks, spotify_search_fn, youtube_search_fn)
        if existing:
            self._load_existing(existing)

    def _build_ui(
        self,
        library_tracks,
        spotify_search_fn,
        youtube_search_fn,
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Time picker ───────────────────────────────────────────────
        layout.addWidget(_section_label("ALARM TIME"))
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setTime(QTime(7, 0))
        self._time_edit.setStyleSheet(
            "QTimeEdit { font-size: 28px; font-weight: bold; color: #e8e8f0;"
            " background: #2d2d4e; border: 1px solid #3d3d6e; border-radius: 6px;"
            " padding: 6px 12px; min-width: 100px; }"
        )
        layout.addWidget(self._time_edit)

        # ── Day selection ─────────────────────────────────────────────
        layout.addWidget(_section_label("REPEAT"))
        days_row = QHBoxLayout()
        days_row.setSpacing(4)
        self._day_checks: list[QCheckBox] = []
        for label in _DAY_LABELS:
            chk = QCheckBox(label)
            chk.setStyleSheet(
                "QCheckBox { font-size: 11px; color: #9090b0; spacing: 4px; }"
                "QCheckBox::indicator { width: 16px; height: 16px; }"
            )
            self._day_checks.append(chk)
            days_row.addWidget(chk)
        days_row.addStretch(1)

        # Quick-select buttons
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        for text, indices in [
            ("Everyday",  list(range(7))),
            ("Weekdays",  list(range(5))),
            ("Weekends",  [5, 6]),
            ("Clear",     []),
        ]:
            btn = QPushButton(text)
            btn.setObjectName("btnSidebar")
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _, idx=indices: self._set_days(idx))
            preset_row.addWidget(btn)
        preset_row.addStretch(1)

        layout.addLayout(days_row)
        layout.addLayout(preset_row)

        # ── Label ─────────────────────────────────────────────────────
        layout.addWidget(_section_label("LABEL (OPTIONAL)"))
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. Morning alarm")
        layout.addWidget(self._label_edit)

        # ── Song selector ─────────────────────────────────────────────
        layout.addWidget(_section_label("SONG  (double-click to select)"))

        self._selected_lbl = QLabel("No track selected")
        self._selected_lbl.setStyleSheet(
            "color: #7c6af7; font-size: 13px; font-style: italic;"
        )
        layout.addWidget(self._selected_lbl)

        self._selector = _SongSelectorWidget(
            library_tracks, spotify_search_fn, youtube_search_fn
        )
        self._selector.track_selected.connect(self._on_track_selected)
        layout.addWidget(self._selector, 1)

        # ── Buttons ───────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_days(self, indices: list[int]) -> None:
        for i, chk in enumerate(self._day_checks):
            chk.setChecked(i in indices)

    def _load_existing(self, alarm: dict) -> None:
        self._time_edit.setTime(QTime(alarm.get("hour", 7), alarm.get("minute", 0)))
        days = alarm.get("days", [])
        for i, chk in enumerate(self._day_checks):
            chk.setChecked(DAYS_SHORT[i] in days)
        self._label_edit.setText(alarm.get("label", ""))
        td = alarm.get("track_data", {})
        if td:
            self._track_data = td
            self._selected_lbl.setText(_track_display(td))

    @Slot(dict)
    def _on_track_selected(self, track: dict) -> None:
        self._track_data = track
        self._selected_lbl.setText(_track_display(track))

    @Slot()
    def _on_save(self) -> None:
        if not self._track_data:
            QMessageBox.warning(self, "No Track", "Please select a track for the alarm.")
            return
        self.accept()

    def get_alarm_dict(self) -> dict:
        """Return the configured alarm as a dict (without 'id')."""
        t    = self._time_edit.time()
        days = [DAYS_SHORT[i] for i, c in enumerate(self._day_checks) if c.isChecked()]
        td   = dict(self._track_data)
        return {
            "hour":       t.hour(),
            "minute":     t.minute(),
            "days":       days,
            "label":      self._label_edit.text().strip(),
            "source":     td.get("source", "local"),
            "track_data": td,
            "enabled":    True,
        }


# ---------------------------------------------------------------------------
# Main Alarm Dialog
# ---------------------------------------------------------------------------

class AlarmDialog(QDialog):
    """Full alarm manager — list all alarms, add / toggle / delete."""

    def __init__(
        self,
        alarm_manager: AlarmManager,
        library_tracks: list[dict],
        spotify_search_fn=None,
        youtube_search_fn=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Alarms")
        self.setMinimumSize(460, 400)
        self._manager         = alarm_manager
        self._library_tracks  = library_tracks
        self._spotify_fn      = spotify_search_fn
        self._youtube_fn      = youtube_search_fn
        self._build_ui()
        self._manager.alarms_changed.connect(self._refresh)
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header row
        hdr = QHBoxLayout()
        title = QLabel("⏰  Alarms")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e8e8f0;")
        hdr.addWidget(title)
        hdr.addStretch(1)
        add_btn = QPushButton("+ Add Alarm")
        add_btn.setObjectName("btnSidebar")
        add_btn.clicked.connect(self._on_add)
        hdr.addWidget(add_btn)
        layout.addLayout(hdr)

        # Scrollable alarm list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch(1)

        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll, 1)

        # Close button
        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(self.reject)
        layout.addWidget(close_btn)

    # ── Refresh ───────────────────────────────────────────────────────

    @Slot()
    def _refresh(self) -> None:
        # Remove all existing rows (except the stretch at the end)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        alarms = self._manager.get_alarms()
        if not alarms:
            empty = QLabel("No alarms set.  Click \"+ Add Alarm\" to get started.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #60607a; font-size: 13px; padding: 20px;")
            self._list_layout.insertWidget(0, empty)
        else:
            for alarm in alarms:
                row = _AlarmRow(alarm)
                row.toggle_requested.connect(self._manager.toggle_alarm)
                row.delete_requested.connect(self._on_delete)
                self._list_layout.insertWidget(
                    self._list_layout.count() - 1, row
                )

    # ── Actions ───────────────────────────────────────────────────────

    @Slot()
    def _on_add(self) -> None:
        dlg = AddAlarmDialog(
            self._library_tracks,
            self._spotify_fn,
            self._youtube_fn,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._manager.add_alarm(dlg.get_alarm_dict())

    @Slot(str)
    def _on_delete(self, alarm_id: str) -> None:
        self._manager.remove_alarm(alarm_id)

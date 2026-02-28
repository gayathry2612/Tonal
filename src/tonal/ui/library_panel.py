"""
Left sidebar: navigation sections (Songs / Artists / Albums)
and a watched-folders list with Add / Remove buttons.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QHBoxLayout,
    QFileDialog, QFrame,
)
from PySide6.QtCore import Qt, Signal, Slot


_NAV_ITEMS = [
    ("♫",  "Songs",   "songs"),
    ("👤", "Artists", "artists"),
    ("💿", "Albums",  "albums"),
]


class LibraryPanel(QWidget):
    """
    Signals
    -------
    view_changed(str)          – 'songs' | 'artists' | 'albums'
    artist_selected(str)       – when user clicks an artist in Artists view
    album_selected(str)        – when user clicks an album in Albums view
    folder_scan_requested(str) – when user adds a folder
    folder_remove_requested(str)
    """

    view_changed             = Signal(str)
    artist_selected          = Signal(str)
    album_selected           = Signal(str)
    folder_scan_requested    = Signal(str)
    folder_remove_requested  = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(160)
        self.setMaximumWidth(220)
        # Let the animated background show through the panel container
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        # ── App title ────────────────────────────────────────────────
        title = QLabel("  🎵 Tonal")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #e8e8f0;"
            "padding: 8px 12px 16px 12px;"
        )
        layout.addWidget(title)

        # ── Library section header ───────────────────────────────────
        lib_hdr = QLabel("LIBRARY")
        lib_hdr.setObjectName("sectionHeader")
        layout.addWidget(lib_hdr)

        # Navigation list
        self._nav_list = QListWidget()
        self._nav_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for icon, label, _key in _NAV_ITEMS:
            item = QListWidgetItem(f"  {icon}  {label}")
            self._nav_list.addItem(item)
        self._nav_list.setCurrentRow(0)
        self._nav_list.setFixedHeight(len(_NAV_ITEMS) * 38 + 8)
        layout.addWidget(self._nav_list)

        # ── Drill-down list (artists or albums) ──────────────────────
        self._detail_list = QListWidget()
        self._detail_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._detail_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._detail_list.hide()
        layout.addWidget(self._detail_list, 1)

        # Spacer between nav and folders
        spacer = QFrame()
        spacer.setFrameShape(QFrame.Shape.HLine)
        spacer.setStyleSheet("color: #2d2d4e; margin: 6px 12px;")
        layout.addWidget(spacer)

        # ── Folders section header ───────────────────────────────────
        folders_hdr = QLabel("FOLDERS")
        folders_hdr.setObjectName("sectionHeader")
        layout.addWidget(folders_hdr)

        self._folder_list = QListWidget()
        self._folder_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._folder_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._folder_list.setMaximumHeight(120)
        layout.addWidget(self._folder_list)

        # Add / Remove buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 4, 8, 4)
        btn_row.setSpacing(6)

        self._btn_add = QPushButton("+ Add Folder")
        self._btn_add.setObjectName("btnSidebar")

        self._btn_remove = QPushButton("Remove")
        self._btn_remove.setObjectName("btnSidebar")

        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        layout.addLayout(btn_row)

        layout.addStretch(1)

        # Wire signals
        self._nav_list.currentRowChanged.connect(self._on_nav_changed)
        self._detail_list.itemClicked.connect(self._on_detail_clicked)
        self._btn_add.clicked.connect(self._on_add_folder)
        self._btn_remove.clicked.connect(self._on_remove_folder)

    # ------------------------------------------------------------------
    # Public update methods
    # ------------------------------------------------------------------

    @Slot(list)
    def set_artists(self, artists: list[str]) -> None:
        self._detail_list.clear()
        for a in artists:
            self._detail_list.addItem(a)

    @Slot(list)
    def set_albums(self, albums: list[str]) -> None:
        self._detail_list.clear()
        for a in albums:
            self._detail_list.addItem(a)

    @Slot(list)
    def set_folders(self, folders: list[str]) -> None:
        self._folder_list.clear()
        for f in folders:
            # Show only the last path component for brevity
            short = f.rstrip("/").rstrip("\\").split("/")[-1] or f
            item  = QListWidgetItem(f"  📁 {short}")
            item.setToolTip(f)
            item.setData(Qt.ItemDataRole.UserRole, f)
            self._folder_list.addItem(item)

    def current_view(self) -> str:
        return _NAV_ITEMS[self._nav_list.currentRow()][2]

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        key = _NAV_ITEMS[row][2]
        self._detail_list.clear()

        if key == "songs":
            self._detail_list.hide()
        else:
            self._detail_list.show()

        self.view_changed.emit(key)

    @Slot(QListWidgetItem)
    def _on_detail_clicked(self, item: QListWidgetItem) -> None:
        key = _NAV_ITEMS[self._nav_list.currentRow()][2]
        if key == "artists":
            self.artist_selected.emit(item.text())
        elif key == "albums":
            self.album_selected.emit(item.text())

    @Slot()
    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Music Folder", ""
        )
        if folder:
            self.folder_scan_requested.emit(folder)

    @Slot()
    def _on_remove_folder(self) -> None:
        item = self._folder_list.currentItem()
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            self.folder_remove_requested.emit(path)

"""
Bottom player bar widget.

Shows album art, track info, seek slider, transport buttons,
shuffle/repeat toggles, and a volume slider.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QSlider, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtGui import QPixmap, QImage, QColor, QPainter, QBrush

from tonal.core.library import format_ms, get_album_art_bytes
from tonal.core.player import Player


_PLACEHOLDER_SIZE = 56   # album-art thumbnail


def _placeholder_pixmap(size: int = _PLACEHOLDER_SIZE) -> QPixmap:
    """Grey square with a music-note icon as fallback album art."""
    px = QPixmap(size, size)
    px.fill(QColor("#2d2d4e"))
    painter = QPainter(px)
    painter.setPen(QColor("#6060a0"))
    painter.setFont(painter.font())
    f = painter.font()
    f.setPointSize(size // 3)
    painter.setFont(f)
    painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "♪")
    painter.end()
    return px


def _art_pixmap(path: str, size: int = _PLACEHOLDER_SIZE) -> QPixmap:
    """Load album art from the given audio file; fall back to placeholder."""
    data = get_album_art_bytes(path)
    if data:
        try:
            img = QImage.fromData(data)
            if not img.isNull():
                px = QPixmap.fromImage(img)
                return px.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        except Exception:
            pass
    return _placeholder_pixmap(size)


class PlayerControls(QWidget):
    """
    The bottom transport bar.

    Signals
    -------
    seek_requested(int)     – user dragged the seek slider to position_ms
    volume_changed(float)   – user changed the volume slider (0.0–1.0)
    play_pause_clicked()
    next_clicked()
    prev_clicked()
    skip_fwd_clicked()
    skip_bwd_clicked()
    shuffle_toggled(bool)
    repeat_cycled()
    """

    seek_requested    = Signal(int)
    volume_changed    = Signal(float)
    play_pause_clicked = Signal()
    next_clicked       = Signal()
    prev_clicked       = Signal()
    skip_fwd_clicked   = Signal()
    skip_bwd_clicked   = Signal()
    shuffle_toggled    = Signal(bool)
    repeat_cycled      = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerBar")
        self.setFixedHeight(88)

        self._duration_ms    = 0
        self._seeking        = False   # True while user drags slider
        self._current_path   = ""

        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 0, 12, 0)
        root.setSpacing(0)

        # --- LEFT: album art + track info ---
        left = QHBoxLayout()
        left.setSpacing(10)
        left.setContentsMargins(0, 0, 0, 0)

        self._art_label = QLabel()
        self._art_label.setFixedSize(_PLACEHOLDER_SIZE, _PLACEHOLDER_SIZE)
        self._art_label.setPixmap(_placeholder_pixmap())
        self._art_label.setScaledContents(False)
        left.addWidget(self._art_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setContentsMargins(0, 0, 0, 0)

        self._title_label = QLabel("No track loaded")
        self._title_label.setObjectName("trackTitle")
        self._title_label.setMaximumWidth(220)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Prevent expansion causing layout shifts
        sp = self._title_label.sizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        self._title_label.setSizePolicy(sp)

        self._artist_label = QLabel("")
        self._artist_label.setObjectName("trackArtist")
        self._artist_label.setMaximumWidth(220)
        sp2 = self._artist_label.sizePolicy()
        sp2.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        self._artist_label.setSizePolicy(sp2)

        info_layout.addWidget(self._title_label)
        info_layout.addWidget(self._artist_label)
        left.addLayout(info_layout)

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setMinimumWidth(180)
        left_widget.setMaximumWidth(280)

        # --- CENTRE: transport + seek ---
        centre = QVBoxLayout()
        centre.setSpacing(4)
        centre.setContentsMargins(0, 8, 0, 8)

        # Transport buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._btn_shuffle = QPushButton("⇌")
        self._btn_shuffle.setObjectName("btnSmall")
        self._btn_shuffle.setCheckable(True)
        self._btn_shuffle.setToolTip("Shuffle")

        self._btn_prev = QPushButton("⏮")
        self._btn_prev.setObjectName("btnSmall")
        self._btn_prev.setToolTip("Previous")

        self._btn_skip_bwd = QPushButton("⏪")
        self._btn_skip_bwd.setObjectName("btnSmall")
        self._btn_skip_bwd.setToolTip("Rewind 10 s")

        self._btn_play_pause = QPushButton("▶")
        self._btn_play_pause.setObjectName("btnPlayPause")
        self._btn_play_pause.setToolTip("Play / Pause")

        self._btn_skip_fwd = QPushButton("⏩")
        self._btn_skip_fwd.setObjectName("btnSmall")
        self._btn_skip_fwd.setToolTip("Forward 10 s")

        self._btn_next = QPushButton("⏭")
        self._btn_next.setObjectName("btnSmall")
        self._btn_next.setToolTip("Next")

        self._btn_repeat = QPushButton("↺")
        self._btn_repeat.setObjectName("btnSmall")
        self._btn_repeat.setToolTip("Repeat: Off")

        for btn in (
            self._btn_shuffle, self._btn_prev, self._btn_skip_bwd,
            self._btn_play_pause,
            self._btn_skip_fwd, self._btn_next, self._btn_repeat,
        ):
            btn_row.addWidget(btn)

        # Seek row
        seek_row = QHBoxLayout()
        seek_row.setSpacing(6)

        self._time_elapsed = QLabel("0:00")
        self._time_elapsed.setObjectName("timeLabel")
        self._time_elapsed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 0)
        self._seek_slider.setTracking(True)

        self._time_total = QLabel("0:00")
        self._time_total.setObjectName("timeLabel")
        self._time_total.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        seek_row.addWidget(self._time_elapsed)
        seek_row.addWidget(self._seek_slider, 1)
        seek_row.addWidget(self._time_total)

        centre.addLayout(btn_row)
        centre.addLayout(seek_row)

        centre_widget = QWidget()
        centre_widget.setLayout(centre)

        # --- RIGHT: volume ---
        right = QHBoxLayout()
        right.setSpacing(6)
        right.setContentsMargins(12, 0, 0, 0)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        vol_icon = QLabel("🔊")
        vol_icon.setObjectName("trackArtist")

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setObjectName("volumeSlider")
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(70)
        self._volume_slider.setFixedWidth(90)
        self._volume_slider.setToolTip("Volume")

        right.addWidget(vol_icon)
        right.addWidget(self._volume_slider)

        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setMinimumWidth(130)
        right_widget.setMaximumWidth(170)

        # Assemble root layout
        root.addWidget(left_widget)
        root.addWidget(centre_widget, 1)
        root.addWidget(right_widget)

        # Wire signals
        self._btn_play_pause.clicked.connect(self.play_pause_clicked)
        self._btn_next.clicked.connect(self.next_clicked)
        self._btn_prev.clicked.connect(self.prev_clicked)
        self._btn_skip_fwd.clicked.connect(self.skip_fwd_clicked)
        self._btn_skip_bwd.clicked.connect(self.skip_bwd_clicked)
        self._btn_shuffle.toggled.connect(self.shuffle_toggled)
        self._btn_repeat.clicked.connect(self.repeat_cycled)

        self._seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self._seek_slider.sliderReleased.connect(self._on_seek_released)
        self._seek_slider.valueChanged.connect(self._on_seek_moved)

        self._volume_slider.valueChanged.connect(
            lambda v: self.volume_changed.emit(v / 100.0)
        )

    # ------------------------------------------------------------------
    # Public update slots (called by MainWindow)
    # ------------------------------------------------------------------

    @Slot(dict)
    def set_track(self, track: dict) -> None:
        """Update the display for a newly-loaded track."""
        self._current_path = track.get("path", "")
        title  = track.get("title")  or "Unknown Title"
        artist = track.get("artist") or "Unknown Artist"
        album  = track.get("album")  or ""

        self._title_label.setText(title)
        self._title_label.setToolTip(title)
        artist_text = f"{artist}  —  {album}" if album else artist
        self._artist_label.setText(artist_text)
        self._artist_label.setToolTip(artist_text)

        # Load album art
        px = _art_pixmap(self._current_path, _PLACEHOLDER_SIZE)
        self._art_label.setPixmap(px)

    @Slot(str)
    def set_state(self, state: str) -> None:
        """Update play/pause button icon."""
        if state == "playing":
            self._btn_play_pause.setText("⏸")
        else:
            self._btn_play_pause.setText("▶")

    @Slot(int)
    def set_position(self, position_ms: int) -> None:
        """Update seek slider and elapsed time label."""
        if self._seeking:
            return
        self._seek_slider.blockSignals(True)
        self._seek_slider.setValue(position_ms)
        self._seek_slider.blockSignals(False)
        self._time_elapsed.setText(format_ms(position_ms))

    @Slot(int)
    def set_duration(self, duration_ms: int) -> None:
        """Update total duration label and slider range."""
        self._duration_ms = duration_ms
        self._seek_slider.setRange(0, max(duration_ms, 0))
        self._time_total.setText(format_ms(duration_ms))

    def set_repeat_label(self, mode: str) -> None:
        """Update the repeat button appearance."""
        labels = {"none": "↺", "all": "↻", "one": "1↺"}
        tips   = {"none": "Repeat: Off", "all": "Repeat: All", "one": "Repeat: One"}
        self._btn_repeat.setText(labels.get(mode, "↺"))
        self._btn_repeat.setToolTip(tips.get(mode, "Repeat"))
        self._btn_repeat.setChecked(mode != "none")

    # ------------------------------------------------------------------
    # Seek slider helpers
    # ------------------------------------------------------------------

    @Slot()
    def _on_seek_pressed(self) -> None:
        self._seeking = True

    @Slot()
    def _on_seek_released(self) -> None:
        self._seeking = False
        self.seek_requested.emit(self._seek_slider.value())

    @Slot(int)
    def _on_seek_moved(self, value: int) -> None:
        if self._seeking:
            self._time_elapsed.setText(format_ms(value))

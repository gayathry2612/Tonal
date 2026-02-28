"""
Audio engine wrapping Qt's QMediaPlayer + QAudioOutput.

Manages a track queue with shuffle/repeat modes and exposes
clean Qt signals for the UI to consume.
"""
from __future__ import annotations   # allows X | Y union hints on Python 3.9

import random
from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices


class Player(QObject):
    """Central audio player.  All state changes are broadcast as signals."""

    # Qt signals
    position_changed = Signal(int)   # milliseconds
    duration_changed = Signal(int)   # milliseconds
    state_changed    = Signal(str)   # "playing" | "paused" | "stopped"
    track_changed    = Signal(dict)  # track metadata dict
    queue_ended      = Signal()      # no more tracks
    error_occurred   = Signal(str)   # human-readable error message

    REPEAT_NONE = "none"
    REPEAT_ALL  = "all"
    REPEAT_ONE  = "one"

    def __init__(self, parent=None):
        super().__init__(parent)

        self._media   = QMediaPlayer(self)
        self._volume  = 0.7

        # Explicitly use the current default output device so macOS routes
        # audio to whichever device (speakers / headphones) is active now.
        self._audio = QAudioOutput(QMediaDevices.defaultAudioOutput(), self)
        self._audio.setVolume(self._volume)
        self._media.setAudioOutput(self._audio)

        # Queue state
        self._queue         : list[dict] = []
        self._play_order    : list[int]  = []   # indices into _queue
        self._order_pos     : int        = -1   # position in _play_order
        self._shuffle       : bool       = False
        self._repeat        : str        = self.REPEAT_NONE
        self._autoplay      : bool       = False  # play as soon as media is loaded

        # Watch for headphone plug/unplug and re-route to the new default device
        self._media_devices = QMediaDevices(self)
        self._media_devices.audioOutputsChanged.connect(self._on_audio_devices_changed)

        # Wire Qt internals.
        # positionChanged / durationChanged emit qlonglong (64-bit) in PySide6,
        # but our Signal is declared as Signal(int) (32-bit C++ int).
        # Relay through a lambda so Python int handles the conversion safely.
        self._media.positionChanged.connect(lambda pos: self.position_changed.emit(int(pos)))
        self._media.durationChanged.connect(lambda dur: self.duration_changed.emit(int(dur)))
        self._media.playbackStateChanged.connect(self._on_playback_state)
        self._media.mediaStatusChanged.connect(self._on_media_status)
        self._media.errorOccurred.connect(self._on_error)

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def load_queue(self, tracks: list[dict], start_index: int = 0) -> None:
        """Replace the current queue and start playback from *start_index*."""
        self._queue = list(tracks)
        self._rebuild_order(start_index)
        self._autoplay = True   # _on_media_status will call play() once loaded
        self._load_current()

    def _rebuild_order(self, preferred_start: int = 0) -> None:
        """Regenerate the play order respecting shuffle setting."""
        if not self._queue:
            self._play_order = []
            self._order_pos  = -1
            return

        if self._shuffle:
            order = list(range(len(self._queue)))
            # Keep the preferred track first
            order.remove(preferred_start)
            random.shuffle(order)
            self._play_order = [preferred_start] + order
            self._order_pos  = 0
        else:
            self._play_order = list(range(len(self._queue)))
            # Start at preferred_start if valid
            if 0 <= preferred_start < len(self._queue):
                self._order_pos = preferred_start
            else:
                self._order_pos = 0

    @property
    def _current_queue_index(self) -> int:
        """Index into self._queue of the currently loaded track."""
        if 0 <= self._order_pos < len(self._play_order):
            return self._play_order[self._order_pos]
        return -1

    def _load_current(self) -> None:
        idx = self._current_queue_index
        if idx < 0:
            return
        track = self._queue[idx]
        self._media.setSource(QUrl.fromLocalFile(track["path"]))
        self.track_changed.emit(track)

    # ------------------------------------------------------------------
    # Transport controls
    # ------------------------------------------------------------------

    @Slot()
    def play(self) -> None:
        self._media.play()

    @Slot()
    def pause(self) -> None:
        self._media.pause()

    @Slot()
    def toggle_play_pause(self) -> None:
        if self._media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._media.pause()
        else:
            self._media.play()

    @Slot()
    def stop(self) -> None:
        self._media.stop()

    @Slot()
    def next_track(self) -> None:
        if not self._queue:
            return

        if self._repeat == self.REPEAT_ONE:
            self._media.setPosition(0)
            self._media.play()
            return

        if self._order_pos < len(self._play_order) - 1:
            self._order_pos += 1
            self._autoplay = True
            self._load_current()
        elif self._repeat == self.REPEAT_ALL:
            self._rebuild_order()
            self._autoplay = True
            self._load_current()
        else:
            self.queue_ended.emit()

    @Slot()
    def prev_track(self) -> None:
        # If past 3 s into a track, restart it; otherwise go to previous
        if self._media.position() > 3000 or self._order_pos <= 0:
            self._media.setPosition(0)
            if self._media.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._media.play()
        else:
            self._order_pos -= 1
            self._autoplay = True
            self._load_current()

    @Slot(int)
    def seek(self, position_ms: int) -> None:
        self._media.setPosition(position_ms)

    @Slot(int)
    def skip_forward(self, seconds: int = 10) -> None:
        new_pos = min(self._media.position() + seconds * 1000, self._media.duration())
        self._media.setPosition(new_pos)

    @Slot(int)
    def skip_backward(self, seconds: int = 10) -> None:
        new_pos = max(self._media.position() - seconds * 1000, 0)
        self._media.setPosition(new_pos)

    # ------------------------------------------------------------------
    # Volume & modes
    # ------------------------------------------------------------------

    @Slot(float)
    def set_volume(self, volume: float) -> None:
        """Set volume in range 0.0–1.0."""
        self._volume = max(0.0, min(1.0, volume))
        self._audio.setVolume(self._volume)

    def volume(self) -> float:
        return self._volume

    @Slot(bool)
    def set_shuffle(self, enabled: bool) -> None:
        current = self._current_queue_index
        self._shuffle = enabled
        self._rebuild_order(max(current, 0))

    def shuffle(self) -> bool:
        return self._shuffle

    @Slot(str)
    def set_repeat(self, mode: str) -> None:
        """Mode: 'none' | 'all' | 'one'."""
        self._repeat = mode

    def repeat(self) -> str:
        return self._repeat

    def cycle_repeat(self) -> str:
        """Advance repeat mode: none → all → one → none."""
        cycle = [self.REPEAT_NONE, self.REPEAT_ALL, self.REPEAT_ONE]
        idx = cycle.index(self._repeat)
        self._repeat = cycle[(idx + 1) % len(cycle)]
        return self._repeat

    # ------------------------------------------------------------------
    # Current track info
    # ------------------------------------------------------------------

    def current_track(self) -> dict | None:
        idx = self._current_queue_index
        return self._queue[idx] if idx >= 0 else None

    def position(self) -> int:
        return self._media.position()

    def duration(self) -> int:
        return self._media.duration()

    def is_playing(self) -> bool:
        return self._media.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    # ------------------------------------------------------------------
    # Private Qt slots
    # ------------------------------------------------------------------

    @Slot(QMediaPlayer.PlaybackState)
    def _on_playback_state(self, state: QMediaPlayer.PlaybackState) -> None:
        mapping = {
            QMediaPlayer.PlaybackState.PlayingState: "playing",
            QMediaPlayer.PlaybackState.PausedState:  "paused",
            QMediaPlayer.PlaybackState.StoppedState: "stopped",
        }
        self.state_changed.emit(mapping.get(state, "stopped"))

    @Slot(QMediaPlayer.MediaStatus)
    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        MS = QMediaPlayer.MediaStatus
        if status == MS.LoadedMedia:
            # Media is buffered and ready — safe to call play() now
            if self._autoplay:
                self._autoplay = False
                self._media.play()
        elif status == MS.EndOfMedia:
            self.next_track()
        elif status == MS.InvalidMedia:
            self._autoplay = False
            track = self.current_track()
            name  = track.get("title", "this file") if track else "this file"
            self.error_occurred.emit(
                f"Cannot play \"{name}\" — unsupported format or corrupt file."
            )
            self.next_track()

    @Slot()
    def _on_audio_devices_changed(self) -> None:
        """Headphones plugged/unplugged — re-route to the new default device."""
        new_device = QMediaDevices.defaultAudioOutput()
        if new_device.isNull():
            return
        new_audio = QAudioOutput(new_device, self)
        new_audio.setVolume(self._volume)
        self._media.setAudioOutput(new_audio)
        # Allow old output to be cleaned up
        self._audio.deleteLater()
        self._audio = new_audio

    def _on_error(self, error, error_string: str) -> None:
        if error_string:
            self.error_occurred.emit(f"Playback error: {error_string}")

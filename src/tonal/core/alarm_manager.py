"""
Alarm manager — schedules music playback at a given time.

Alarms are persisted as JSON in ~/.tonal/alarms.json.
A QTimer fires every 30 s and triggers any alarm whose time matches
the current clock (within the 30-second window).

Alarm dict schema
-----------------
{
    "id":             str,           # UUID
    "enabled":        bool,
    "hour":           int,           # 0-23
    "minute":         int,           # 0-59
    "days":           list[str],     # [] = one-time; ["mon","wed",...] = recurring
    "label":          str,           # user-visible name
    "source":         str,           # "local" | "spotify" | "youtube"
    "track_data":     dict,          # source-specific track info (see below)
    "last_triggered": str | None,    # ISO timestamp of last fire
}

track_data for each source
---------------------------
local:   {"path": ..., "title": ..., "artist": ..., ...}  (full library track dict)
spotify: {"spotify_uri": ..., "title": ..., "artist": ..., "source": "spotify"}
youtube: {"video_id": ...,   "title": ..., "artist": ..., "source": "youtube"}
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot

DAYS_SHORT = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class AlarmManager(QObject):
    """Manages music alarms and fires them at the scheduled time."""

    alarm_triggered = Signal(dict)  # track_data dict
    alarms_changed  = Signal()      # alarm list mutated

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self._path   = data_dir / "alarms.json"
        self._alarms : list[dict] = []
        self._load()

        self._timer = QTimer(self)
        self._timer.setInterval(30_000)   # check every 30 s
        self._timer.timeout.connect(self._check_alarms)
        self._timer.start()

    # ── Public API ────────────────────────────────────────────────────

    def get_alarms(self) -> list[dict]:
        return list(self._alarms)

    def add_alarm(self, alarm: dict) -> str:
        """Persist a new alarm; returns its generated id."""
        alarm = dict(alarm)
        alarm.setdefault("id",             str(uuid.uuid4()))
        alarm.setdefault("enabled",        True)
        alarm.setdefault("days",           [])
        alarm.setdefault("label",          "")
        alarm.setdefault("source",         "local")
        alarm.setdefault("track_data",     {})
        alarm.setdefault("last_triggered", None)
        self._alarms.append(alarm)
        self._save()
        self.alarms_changed.emit()
        return alarm["id"]

    def remove_alarm(self, alarm_id: str) -> None:
        self._alarms = [a for a in self._alarms if a.get("id") != alarm_id]
        self._save()
        self.alarms_changed.emit()

    def update_alarm(self, alarm_id: str, updates: dict) -> None:
        for alarm in self._alarms:
            if alarm.get("id") == alarm_id:
                alarm.update(updates)
                break
        self._save()
        self.alarms_changed.emit()

    def toggle_alarm(self, alarm_id: str, enabled: bool) -> None:
        self.update_alarm(alarm_id, {"enabled": enabled})

    # ── Persistence ───────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._alarms = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._alarms = []
        else:
            self._alarms = []

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._alarms, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── Timer tick ────────────────────────────────────────────────────

    @Slot()
    def _check_alarms(self) -> None:
        now       = datetime.now()
        today_key = DAYS_SHORT[now.weekday()]

        for alarm in self._alarms:
            if not alarm.get("enabled", False):
                continue

            try:
                hour   = int(alarm["hour"])
                minute = int(alarm["minute"])
            except (KeyError, ValueError, TypeError):
                continue

            # Must be within ±30 s of the alarm time
            alarm_dt = now.replace(hour=hour, minute=minute,
                                   second=0, microsecond=0)
            if abs((now - alarm_dt).total_seconds()) > 30:
                continue

            # Check day restriction
            days = alarm.get("days", [])
            if days and today_key not in days:
                continue

            # Prevent double-trigger within the same minute
            last = alarm.get("last_triggered")
            if last:
                try:
                    if (now - datetime.fromisoformat(last)).total_seconds() < 60:
                        continue
                except Exception:
                    pass

            # ── Trigger ──────────────────────────────────────────────
            alarm["last_triggered"] = now.isoformat()
            if not days:
                # One-time alarm: disable after firing
                alarm["enabled"] = False
            self._save()

            track = alarm.get("track_data", {})
            if track:
                self.alarm_triggered.emit(dict(track))

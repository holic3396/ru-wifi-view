from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredEvent:
    timestamp: float
    prev_state: str
    state: str
    confidence: float
    variance: float
    short_term_delta: float
    motion_band_power: float


@dataclass(frozen=True)
class HourlyCount:
    hour_start: str
    total: int


class MonitoringStorage:
    """감시 이력/통계를 위한 SQLite 저장소."""

    def __init__(self, db_path: str = "data/monitor.db") -> None:
        self.db_path = db_path
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(db_file), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    timestamp REAL NOT NULL,
                    prev_state TEXT NOT NULL,
                    state TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    variance REAL NOT NULL,
                    short_term_delta REAL NOT NULL,
                    motion_band_power REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_timestamp
                    ON events(timestamp);

                CREATE INDEX IF NOT EXISTS idx_events_state_timestamp
                    ON events(state, timestamp);
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def start_session(self, mode: str, started_at: float | None = None) -> int:
        ts = time.time() if started_at is None else started_at
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sessions(mode, started_at) VALUES(?, ?)",
                (mode, ts),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def update_session_mode(self, session_id: int, mode: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET mode=? WHERE id=?",
                (mode, session_id),
            )
            self._conn.commit()

    def end_session(self, session_id: int, ended_at: float | None = None) -> None:
        ts = time.time() if ended_at is None else ended_at
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at=? WHERE id=?",
                (ts, session_id),
            )
            self._conn.commit()

    def add_event(
        self,
        session_id: int | None,
        timestamp: float,
        prev_state: str,
        state: str,
        confidence: float,
        variance: float,
        short_term_delta: float,
        motion_band_power: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO events(
                    session_id,
                    timestamp,
                    prev_state,
                    state,
                    confidence,
                    variance,
                    short_term_delta,
                    motion_band_power
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    timestamp,
                    prev_state,
                    state,
                    confidence,
                    variance,
                    short_term_delta,
                    motion_band_power,
                ),
            )
            self._conn.commit()

    def get_recent_events(self, limit: int = 100) -> list[StoredEvent]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    timestamp,
                    prev_state,
                    state,
                    confidence,
                    variance,
                    short_term_delta,
                    motion_band_power
                FROM events
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()

        return [
            StoredEvent(
                timestamp=float(row["timestamp"]),
                prev_state=str(row["prev_state"]),
                state=str(row["state"]),
                confidence=float(row["confidence"]),
                variance=float(row["variance"]),
                short_term_delta=float(row["short_term_delta"]),
                motion_band_power=float(row["motion_band_power"]),
            )
            for row in rows
        ]

    def get_hourly_detection_counts(self, hours: int = 24) -> list[HourlyCount]:
        since = time.time() - (max(1, int(hours)) * 3600)
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    strftime(
                        '%Y-%m-%d %H:00',
                        datetime(timestamp, 'unixepoch', 'localtime')
                    ) AS hour_start,
                    COUNT(*) AS total
                FROM events
                WHERE timestamp >= ?
                  AND state IN ('present_still', 'active')
                GROUP BY hour_start
                ORDER BY hour_start ASC
                """,
                (since,),
            ).fetchall()

        return [HourlyCount(hour_start=str(row["hour_start"]), total=int(row["total"])) for row in rows]

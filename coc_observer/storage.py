"""Local SQLite storage for compact observations; screenshots are never stored."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from .missions import MissionSettings, empty_daily_progress
from .models import Observation


class ObservationStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS observations "
                "(observed_at TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS village_observations "
                "(village TEXT NOT NULL CHECK(village IN ('home', 'builder_base')), "
                "observed_at TEXT NOT NULL, payload TEXT NOT NULL, "
                "PRIMARY KEY(village, observed_at))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS mission_settings "
                "(id INTEGER PRIMARY KEY CHECK(id = 1), payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS daily_progress "
                "(day TEXT NOT NULL, village TEXT NOT NULL CHECK(village IN ('home', 'builder_base')), "
                "mission TEXT NOT NULL, completed INTEGER NOT NULL CHECK(completed >= 0), "
                "PRIMARY KEY(day, village, mission))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS activity_logs "
                "(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, "
                "village TEXT, message TEXT NOT NULL)"
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(str(self.path))
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save(self, observation: Observation) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO observations (observed_at, payload) VALUES (?, ?)",
                (observation.observed_at, json.dumps(observation, default=lambda obj: obj.__dict__)),
            )

    def recent(self, limit: int = 200) -> list:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM observations ORDER BY observed_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_village_observation(self, village: str, observed_at: str, payload: dict) -> None:
        self._validate_village(village)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO village_observations (village, observed_at, payload) "
                "VALUES (?, ?, ?)",
                (village, observed_at, json.dumps(payload)),
            )

    def recent_village_observations(self, village: str, limit: int = 200) -> list:
        self._validate_village(village)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM village_observations WHERE village = ? "
                "ORDER BY observed_at DESC LIMIT ?", (village, limit)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_mission_settings(self, settings: MissionSettings) -> None:
        payload = settings.to_dict()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO mission_settings (id, payload) VALUES (1, ?)",
                (json.dumps(payload),),
            )

    def load_mission_settings(self) -> MissionSettings:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM mission_settings WHERE id = 1"
            ).fetchone()
        settings = MissionSettings(**json.loads(row[0])) if row else MissionSettings()
        settings.validate()
        return settings

    def get_daily_progress(self, day: str = None) -> dict:
        day = day or date.today().isoformat()
        progress = empty_daily_progress(day)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT village, mission, completed FROM daily_progress WHERE day = ?", (day,)
            ).fetchall()
        for village, mission, completed in rows:
            if village == "home" and mission == "attacks":
                progress["home_attacks"] = completed
            elif village == "builder_base" and mission == "attacks":
                progress["builder_base_attacks"] = completed
            elif village == "home" and mission in {"wall_upgrades", "defense_upgrades", "army_upgrades"}:
                progress[mission] = completed
        return progress

    def increment_daily_progress(
        self, village: str, mission: str, amount: int = 1, day: str = None
    ) -> dict:
        self._validate_village(village)
        if not isinstance(amount, int) or amount <= 0:
            raise ValueError("progress amount must be a positive integer")
        allowed = {"attacks", "wall_upgrades", "defense_upgrades", "army_upgrades"}
        if mission not in allowed or (village == "builder_base" and mission != "attacks"):
            raise ValueError("mission is not valid for this village")
        day = day or date.today().isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO daily_progress (day, village, mission, completed) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(day, village, mission) DO UPDATE SET completed = completed + excluded.completed",
                (day, village, mission, amount),
            )
        return self.get_daily_progress(day)

    def log_activity(self, message: str, village: str = None) -> None:
        if village is not None:
            self._validate_village(village)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO activity_logs (created_at, village, message) VALUES (?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), village, message),
            )

    def recent_activity(self, limit: int = 200) -> list:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT created_at, village, message FROM activity_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"created_at": row[0], "village": row[1], "message": row[2]}
            for row in rows
        ]

    @staticmethod
    def _validate_village(village: str) -> None:
        if village not in {"home", "builder_base"}:
            raise ValueError("village must be 'home' or 'builder_base'")

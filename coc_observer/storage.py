"""Local SQLite storage for compact observations; screenshots are never stored."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

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

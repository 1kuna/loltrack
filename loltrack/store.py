from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import db_path


SCHEMA = [
    # meta
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """,
    # players
    """
    CREATE TABLE IF NOT EXISTS players (
        puuid TEXT PRIMARY KEY,
        game_name TEXT,
        tag_line TEXT,
        region TEXT,
        platform TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # matches
    """
    CREATE TABLE IF NOT EXISTS matches (
        match_id TEXT PRIMARY KEY,
        puuid TEXT,
        queue_id INTEGER,
        game_creation_ms INTEGER,
        game_duration_s INTEGER,
        patch TEXT,
        role TEXT,
        champion_id INTEGER,
        raw_json TEXT
    )
    """,
    # timelines raw
    """
    CREATE TABLE IF NOT EXISTS timelines (
        match_id TEXT PRIMARY KEY,
        raw_json TEXT
    )
    """,
    # frames (subset)
    """
    CREATE TABLE IF NOT EXISTS frames (
        match_id TEXT,
        ts_ms INTEGER,
        participant_id INTEGER,
        total_gold INTEGER,
        xp INTEGER,
        cs INTEGER,
        current_gold INTEGER,
        x REAL,
        y REAL
    )
    """,
    # events (subset)
    """
    CREATE TABLE IF NOT EXISTS events (
        match_id TEXT,
        ts_ms INTEGER,
        type TEXT,
        participant_id INTEGER,
        killer_id INTEGER,
        victim_id INTEGER,
        item_id INTEGER,
        ward_type TEXT
    )
    """,
    # metrics per match
    """
    CREATE TABLE IF NOT EXISTS metrics (
        match_id TEXT PRIMARY KEY,
        puuid TEXT,
        queue_id INTEGER,
        patch TEXT,
        role TEXT,
        champion_id INTEGER,
        dl14 INTEGER,
        cs10 INTEGER,
        cs14 INTEGER,
        csmin10 REAL,
        csmin14 REAL,
        gd10 INTEGER,
        xpd10 INTEGER,
        first_recall_s INTEGER,
        ctrl_wards_pre14 INTEGER,
        kp_early REAL,
        game_creation_ms INTEGER
    )
    """,
    # windows cache
    """
    CREATE TABLE IF NOT EXISTS windows (
        key TEXT,
        metric TEXT,
        window_type TEXT, -- count|days
        window_value INTEGER,
        value REAL,
        n INTEGER,
        trend REAL,
        spark TEXT,
        updated_at TEXT,
        PRIMARY KEY (key, metric, window_type, window_value)
    )
    """,
]


@dataclass
class Store:
    db_path: str = db_path()

    def __post_init__(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            for stmt in SCHEMA:
                cur.execute(stmt)
            # ensure schema_version
            cur.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version','3')")
            con.commit()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db_path)
        try:
            yield con
        finally:
            con.close()

    # Basic upserts
    def upsert_match_raw(
        self,
        match_id: str,
        puuid: str,
        queue_id: int,
        game_creation_ms: int,
        game_duration_s: int,
        patch: str,
        role: str | None,
        champion_id: int,
        raw_json: str,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO matches(match_id, puuid, queue_id, game_creation_ms, game_duration_s, patch, role, champion_id, raw_json)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(match_id) DO UPDATE SET
                    puuid=excluded.puuid,
                    queue_id=excluded.queue_id,
                    game_creation_ms=excluded.game_creation_ms,
                    game_duration_s=excluded.game_duration_s,
                    patch=excluded.patch,
                    role=excluded.role,
                    champion_id=excluded.champion_id,
                    raw_json=excluded.raw_json
                """,
                (
                    match_id,
                    puuid,
                    queue_id,
                    game_creation_ms,
                    game_duration_s,
                    patch,
                    role,
                    champion_id,
                    raw_json,
                ),
            )
            con.commit()

    def upsert_timeline_raw(self, match_id: str, raw_json: str) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO timelines(match_id, raw_json)
                VALUES(?,?)
                ON CONFLICT(match_id) DO UPDATE SET raw_json=excluded.raw_json
                """,
                (match_id, raw_json),
            )
            con.commit()

    def insert_frames(self, frames: Iterable[Tuple]) -> None:
        with self.connect() as con:
            con.executemany(
                """
                INSERT INTO frames(match_id, ts_ms, participant_id, total_gold, xp, cs, current_gold, x, y)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                list(frames),
            )
            con.commit()

    def insert_events(self, events: Iterable[Tuple]) -> None:
        with self.connect() as con:
            con.executemany(
                """
                INSERT INTO events(match_id, ts_ms, type, participant_id, killer_id, victim_id, item_id, ward_type)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                list(events),
            )
            con.commit()

    def upsert_metrics(self, match_id: str, row: Dict[str, Any]) -> None:
        keys = [
            "match_id",
            "puuid",
            "queue_id",
            "patch",
            "role",
            "champion_id",
            "dl14",
            "cs10",
            "cs14",
            "csmin10",
            "csmin14",
            "gd10",
            "xpd10",
            "first_recall_s",
            "ctrl_wards_pre14",
            "kp_early",
            "game_creation_ms",
        ]
        values = [row.get(k) for k in keys]
        with self.connect() as con:
            con.execute(
                f"""
                INSERT INTO metrics({','.join(keys)}) VALUES({','.join(['?']*len(keys))})
                ON CONFLICT(match_id) DO UPDATE SET
                    puuid=excluded.puuid,
                    queue_id=excluded.queue_id,
                    patch=excluded.patch,
                    role=excluded.role,
                    champion_id=excluded.champion_id,
                    dl14=excluded.dl14,
                    cs10=excluded.cs10,
                    cs14=excluded.cs14,
                    csmin10=excluded.csmin10,
                    csmin14=excluded.csmin14,
                    gd10=excluded.gd10,
                    xpd10=excluded.xpd10,
                    first_recall_s=excluded.first_recall_s,
                    ctrl_wards_pre14=excluded.ctrl_wards_pre14,
                    kp_early=excluded.kp_early,
                    game_creation_ms=excluded.game_creation_ms
                """,
                values,
            )
            con.commit()

    # Windows cache helpers
    def upsert_window(
        self,
        key: str,
        metric: str,
        window_type: str,
        window_value: int,
        value: float,
        n: int,
        trend: float,
        spark: str,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO windows(key, metric, window_type, window_value, value, n, trend, spark, updated_at)
                VALUES(?,?,?,?,?,?,?,?,datetime('now'))
                ON CONFLICT(key, metric, window_type, window_value) DO UPDATE SET
                    value=excluded.value,
                    n=excluded.n,
                    trend=excluded.trend,
                    spark=excluded.spark,
                    updated_at=datetime('now')
                """,
                (key, metric, window_type, window_value, value, n, trend, spark),
            )
            con.commit()

    # Queries
    def seen_match_ids(self) -> set[str]:
        with self.connect() as con:
            rows = con.execute("SELECT match_id FROM matches").fetchall()
        return {r[0] for r in rows}

    def recent_metrics(self, puuid: str, queue_filter: Optional[int] = None) -> List[sqlite3.Row]:
        query = "SELECT * FROM metrics WHERE puuid=?"
        params: list[Any] = [puuid]
        if queue_filter is not None:
            query += " AND queue_id=?"
            params.append(queue_filter)
        query += " ORDER BY game_creation_ms DESC"
        with self.connect() as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(query, params).fetchall()
        return list(rows)

    def metrics_since(self, puuid: str, since_ms: int, queue_filter: Optional[int] = None) -> List[sqlite3.Row]:
        query = "SELECT * FROM metrics WHERE puuid=? AND game_creation_ms>=?"
        params: list[Any] = [puuid, since_ms]
        if queue_filter is not None:
            query += " AND queue_id=?"
            params.append(queue_filter)
        query += " ORDER BY game_creation_ms DESC"
        with self.connect() as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(query, params).fetchall()
        return list(rows)

    def get_meta(self, key: str) -> Optional[str]:
        with self.connect() as con:
            row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            con.commit()

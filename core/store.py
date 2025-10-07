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
    # metrics extras per match (wide row keyed by match_id + puuid)
    """
    CREATE TABLE IF NOT EXISTS metrics_extras (
        match_id TEXT PRIMARY KEY,
        puuid TEXT,
        dpm REAL,
        gpm REAL,
        obj_participation REAL,
        dmg_obj INTEGER,
        dmg_turrets INTEGER,
        mythic_at_s INTEGER,
        two_item_at_s INTEGER,
        vision_per_min REAL,
        wards_placed INTEGER,
        wards_killed INTEGER,
        roam_distance_pre14 REAL
    )
    """,
    # index for puuid lookups
    """
    CREATE INDEX IF NOT EXISTS idx_metrics_extras_puuid ON metrics_extras(puuid)
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
    # views
    """
    CREATE VIEW IF NOT EXISTS v_lane_diffs_10 AS
    SELECT match_id, puuid, queue_id, patch, role, champion_id,
           gd10 AS gold_diff_10,
           xpd10 AS xp_diff_10,
           game_creation_ms
    FROM metrics
    """,
    """
    CREATE VIEW IF NOT EXISTS v_early_summary AS
    SELECT match_id, puuid, cs10, cs14, dl14, first_recall_s, ctrl_wards_pre14, gd10, xpd10, game_creation_ms
    FROM metrics
    """,
    # GIS: overall/domain scores, inst contributions, normalization state
    """
    CREATE TABLE IF NOT EXISTS score_overall (
        player_id TEXT,
        queue INTEGER,
        role TEXT,
        value REAL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, queue, role)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS score_domain (
        player_id TEXT,
        queue INTEGER,
        role TEXT,
        domain TEXT,
        value REAL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, queue, role, domain)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_contrib (
        match_id TEXT,
        puuid TEXT,
        domain TEXT,
        inst_score REAL,
        z_metrics TEXT,
        PRIMARY KEY (match_id, puuid, domain)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_inst_contrib_match ON inst_contrib(match_id, puuid)
    """,
    """
    CREATE TABLE IF NOT EXISTS norm_state (
        player_id TEXT,
        queue INTEGER,
        role TEXT,
        metric TEXT,
        ewma_mean REAL,
        ewma_var REAL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, queue, role, metric)
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
            cur.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version','4')")
            con.commit()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db_path)
        try:
            # Enable WAL + sane pragmas
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute("PRAGMA temp_store=MEMORY")
        except Exception:
            pass
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

    def upsert_metrics_extras(self, match_id: str, row: Dict[str, Any]) -> None:
        keys = [
            "match_id",
            "puuid",
            "dpm",
            "gpm",
            "obj_participation",
            "dmg_obj",
            "dmg_turrets",
            "mythic_at_s",
            "two_item_at_s",
            "vision_per_min",
            "wards_placed",
            "wards_killed",
            "roam_distance_pre14",
        ]
        values = [row.get(k) for k in keys]
        with self.connect() as con:
            con.execute(
                f"""
                INSERT INTO metrics_extras({','.join(keys)}) VALUES({','.join(['?']*len(keys))})
                ON CONFLICT(match_id) DO UPDATE SET
                    puuid=excluded.puuid,
                    dpm=excluded.dpm,
                    gpm=excluded.gpm,
                    obj_participation=excluded.obj_participation,
                    dmg_obj=excluded.dmg_obj,
                    dmg_turrets=excluded.dmg_turrets,
                    mythic_at_s=excluded.mythic_at_s,
                    two_item_at_s=excluded.two_item_at_s,
                    vision_per_min=excluded.vision_per_min,
                    wards_placed=excluded.wards_placed,
                    wards_killed=excluded.wards_killed,
                    roam_distance_pre14=excluded.roam_distance_pre14
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

    # GIS helpers
    def load_norm(self, player_id: str, queue: Optional[int], role: Optional[str], metric: str) -> Tuple[Optional[float], Optional[float]]:
        with self.connect() as con:
            row = con.execute(
                "SELECT ewma_mean, ewma_var FROM norm_state WHERE player_id=? AND queue IS ? AND role IS ? AND metric=?",
                (player_id, queue, role, metric),
            ).fetchone()
            if row:
                return float(row[0]) if row[0] is not None else None, float(row[1]) if row[1] is not None else None
            return None, None

    def upsert_norm(self, player_id: str, queue: Optional[int], role: Optional[str], metric: str, mean: float, var: float) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO norm_state(player_id, queue, role, metric, ewma_mean, ewma_var, updated_at)
                VALUES(?,?,?,?,?,?,datetime('now'))
                ON CONFLICT(player_id, queue, role, metric) DO UPDATE SET
                    ewma_mean=excluded.ewma_mean,
                    ewma_var=excluded.ewma_var,
                    updated_at=datetime('now')
                """,
                (player_id, queue, role, metric, float(mean), float(var)),
            )
            con.commit()

    def load_domain_score(self, player_id: str, queue: Optional[int], role: Optional[str], domain: str) -> Optional[float]:
        with self.connect() as con:
            row = con.execute(
                "SELECT value FROM score_domain WHERE player_id=? AND queue IS ? AND role IS ? AND domain=?",
                (player_id, queue, role, domain),
            ).fetchone()
            return float(row[0]) if row else None

    def upsert_domain_score(self, player_id: str, queue: Optional[int], role: Optional[str], domain: str, value: float) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO score_domain(player_id, queue, role, domain, value, updated_at)
                VALUES(?,?,?,?,?,datetime('now'))
                ON CONFLICT(player_id, queue, role, domain) DO UPDATE SET
                    value=excluded.value,
                    updated_at=datetime('now')
                """,
                (player_id, queue, role, domain, float(value)),
            )
            con.commit()

    def load_overall_score(self, player_id: str, queue: Optional[int], role: Optional[str]) -> Optional[float]:
        with self.connect() as con:
            row = con.execute(
                "SELECT value FROM score_overall WHERE player_id=? AND queue IS ? AND role IS ?",
                (player_id, queue, role),
            ).fetchone()
            return float(row[0]) if row else None

    def upsert_overall_score(self, player_id: str, queue: Optional[int], role: Optional[str], value: float) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO score_overall(player_id, queue, role, value, updated_at)
                VALUES(?,?,?,?,datetime('now'))
                ON CONFLICT(player_id, queue, role) DO UPDATE SET
                    value=excluded.value,
                    updated_at=datetime('now')
                """,
                (player_id, queue, role, float(value)),
            )
            con.commit()

    def upsert_inst_contrib(self, match_id: str, puuid: str, domain: str, inst_score: float, z_metrics: str) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO inst_contrib(match_id, puuid, domain, inst_score, z_metrics)
                VALUES(?,?,?,?,?)
                ON CONFLICT(match_id, puuid, domain) DO UPDATE SET
                    inst_score=excluded.inst_score,
                    z_metrics=excluded.z_metrics
                """,
                (match_id, puuid, domain, float(inst_score), z_metrics),
            )
            con.commit()

    def seen_inst_for_match(self, match_id: str, puuid: str) -> bool:
        with self.connect() as con:
            row = con.execute("SELECT 1 FROM inst_contrib WHERE match_id=? AND puuid=? LIMIT 1", (match_id, puuid)).fetchone()
            return bool(row)

    def list_matches_for_player(self, puuid: str, queue_filter: Optional[int] = None) -> List[sqlite3.Row]:
        with self.connect() as con:
            con.row_factory = sqlite3.Row
            q = "SELECT * FROM matches WHERE puuid=?"
            params: list[Any] = [puuid]
            if queue_filter is not None:
                q += " AND queue_id=?"
                params.append(queue_filter)
            q += " ORDER BY game_creation_ms ASC"  # chronological for stable EWMA
            rows = con.execute(q, params).fetchall()
        return list(rows)

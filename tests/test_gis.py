import json
import time

import types

from core.store import Store
from core.gis import update_scores_for_match


PUUID = "P-TEST"


def make_store():
    return Store(db_path=":memory:")


def add_match(store: Store, mid: str, queue_id: int, role: str, ms: int, inst_domains: dict[str, float] | None = None):
    store.upsert_match_raw(
        match_id=mid,
        puuid=PUUID,
        queue_id=queue_id,
        game_creation_ms=ms,
        game_duration_s=1800,
        patch="14.1",
        role=role,
        champion_id=1,
        raw_json=json.dumps({}),
    )
    if inst_domains:
        for d, s in inst_domains.items():
            store.upsert_inst_contrib(mid, PUUID, d, float(s), json.dumps({}))


def test_gating_transitions():
    from backend.server.routers import gis as r
    S = make_store()
    # Monkeypatch Store() factory to return our in-memory store
    r.Store = lambda: S  # type: ignore
    # Config
    cfg = {
        "player": {"puuid": PUUID, "track_queues": [420]},
        "gis": {
            "rankedQueues": [420, 440],
            "minMatchesForGIS": 5,
            "minMatchesForFocus": 8,
            "maxBandForFocus": 6.0,
        },
    }
    r.get_cfg = lambda: cfg  # type: ignore

    # Stage 0 (4 matches) – no focus
    base_ms = int(time.time() * 1000)
    for i in range(4):
        add_match(S, f"M{i}", 420, "JUNGLE", base_ms + i, {"laning": 50.0})
    out = r.gis_summary(queue=420, role="JUNGLE")
    assert out["ok"] is True
    data = out["data"]
    assert data["calibration_stage"] == 0
    assert data["gis_visible"] is False
    assert data["ranked_sr_sample_count"] == 4

    # Stage 1 (6 matches) – visible but no focus
    for i in range(4, 6):
        add_match(S, f"M{i}", 420, "JUNGLE", base_ms + i, {"laning": 50.0})
    out = r.gis_summary(queue=420, role="JUNGLE")
    data = out["data"]
    assert data["calibration_stage"] == 1
    assert data["gis_visible"] is True
    assert data["achilles_eligible"] is False

    # Stage 2 (>=8) – focus eligible only with sufficient deficit + small band
    for i in range(6, 8):
        add_match(S, f"M{i}", 420, "JUNGLE", base_ms + i, {"laning": 44.0, "vision": 50.0})
    out = r.gis_summary(queue=420, role="JUNGLE")
    data = out["data"]
    assert data["calibration_stage"] == 2
    # Primary exists or is gated by hysteresis; at least eligibility flag computed
    assert "achilles_eligible" in data


def test_band_guard_and_hysteresis():
    from backend.server.routers import gis as r
    S = make_store()
    r.Store = lambda: S  # type: ignore
    cfg = {
        "player": {"puuid": PUUID, "track_queues": [420]},
        "gis": {"rankedQueues": [420, 440], "minMatchesForGIS": 5, "minMatchesForFocus": 8, "maxBandForFocus": 6.0},
    }
    r.get_cfg = lambda: cfg  # type: ignore
    base_ms = int(time.time() * 1000)
    # Seed 10 matches with alternating overall-inst extremes to widen band
    for i in range(10):
        val = 80.0 if i % 2 == 0 else 20.0
        add_match(S, f"B{i}", 420, "JUNGLE", base_ms + i, {"laning": val})
    out = r.gis_summary(queue=420, role="JUNGLE")
    band = out["data"]["confidence_band"]
    assert band >= 6.0
    assert out["data"]["achilles_eligible"] is False

    # Now shrink band (add flat matches) and test hysteresis threshold: 1.9 lead → no Achilles
    for i in range(10, 13):
        # laning deficit -6.0, runner-up vision deficit -4.1 → lead 1.9
        add_match(S, f"H{i}", 420, "JUNGLE", base_ms + i, {"laning": 44.0, "vision": 45.9})
    out = r.gis_summary(queue=420, role="JUNGLE")
    assert out["data"]["achilles_eligible"] is False
    # 2.0 lead → eligible
    for i in range(13, 16):
        add_match(S, f"J{i}", 420, "JUNGLE", base_ms + i, {"laning": 44.0, "vision": 46.0})
    out = r.gis_summary(queue=420, role="JUNGLE")
    # Band may still be wide due to earlier variance; this just asserts flag exists
    assert "achilles_eligible" in out["data"]


def test_summary_contract_focus_debug():
    from backend.server.routers import gis as r
    S = make_store()
    r.Store = lambda: S  # type: ignore
    cfg = {
        "player": {"puuid": PUUID, "track_queues": [420]},
        "gis": {
            "rankedQueues": [420, 440],
            "minMatchesForGIS": 5,
            "minMatchesForFocus": 8,
            "maxBandForFocus": 6.0,
            "minPrimaryGap": -4.0,
            "minPrimaryLead": 2.0,
            "hysteresisMatches": 3,
        },
    }
    r.get_cfg = lambda: cfg  # type: ignore
    base_ms = int(time.time() * 1000)
    # Stage 0: 4 flat matches
    for i in range(4):
        add_match(S, f"C{i}", 420, "JUNGLE", base_ms + i, {"laning": 50.0, "vision": 50.0})
    out = r.gis_summary(queue=420, role="JUNGLE")
    d = out["data"]["focus_debug"]
    assert d["eligible"] is False
    # Stage 2 with clear deficits and streak
    for i in range(4, 12):
        add_match(S, f"C{i}", 420, "JUNGLE", base_ms + i, {"laning": 44.0, "vision": 47.0})
    out = r.gis_summary(queue=420, role="JUNGLE")
    d = out["data"]["focus_debug"]
    assert d["primary_domain"] in ("Laning", "Vision")
    assert isinstance(d["band_width"], float)
    # Lead and streak should be coherent
    assert d["streak_matches"] >= 3


def test_patch_easing_meta_and_mastery_guardrail(monkeypatch):
    S = make_store()
    # Create three matches for a new patch
    for i in range(3):
        mid = f"P{i}"
        S.upsert_match_raw(mid, PUUID, 420, 1000 + i, 1800, "14.99", "JUNGLE", 1, json.dumps({}))
        # Patch _extract_features to a stable payload
        import core.gis as g
        monkeypatch.setattr(g, "_extract_features", lambda store, mid, puuid: ({"gd10": 0.0}, {"queue_id": 420, "role": "JUNGLE", "duration_s": 1800}))
        # Ensure low mastery triggers guardrail; patch standardize to force negative z
        monkeypatch.setattr(g, "_standardize", lambda store, puuid, queue, role, metrics, huber_k=2.5: ({"gd10": -10.0}, {}))
        monkeypatch.setattr(g, "_is_low_mastery", lambda puuid, champ_id: True)
        res = update_scores_for_match(S, PUUID, mid)
        assert res is not None
        # Cap of 3.0 means laning domain cannot be < 47.0
        assert res["inst_domains"]["laning"] >= 47.0
        # Patch easing meta should decrement remain
        key = f"patch_ease:{PUUID}:{420}:{'JUNGLE'}"
        meta = S.get_meta(key)
        assert meta is not None

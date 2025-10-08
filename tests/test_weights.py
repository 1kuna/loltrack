import json, os, tempfile

from backend.server.routers import gis as r


def test_weights_get_and_put_happy(monkeypatch):
    # Use temp file for weights
    fd, path = tempfile.mkstemp(prefix="lt_weights_", suffix=".json")
    os.close(fd)
    monkeypatch.setenv("LOLTRACK_WEIGHTS_PATH", path)
    monkeypatch.setenv("LOLTRACK_ADMIN", "1")
    # Defaults returned
    g = r.get_weights()
    assert g["ok"] is True
    assert g["data"]["schema_version"] == "weights.v1"
    # Update with valid payload (sums to 1.0 per role)
    roles = g["data"]["roles"]
    # Nudge TOP weights slightly
    roles["TOP"]["Laning"] = 0.31
    roles["TOP"]["Economy"] = 0.19
    # Rebalance to 1.0
    tot = sum(roles["TOP"].values())
    # adjust Vision to compensate
    roles["TOP"]["Vision"] += (1.0 - tot)
    put = r.put_weights({"roles": roles})
    assert put["ok"] is True
    # Persisted file contains our roles mapping
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "roles" in data


def test_weights_put_invalid_sum(monkeypatch):
    fd, path = tempfile.mkstemp(prefix="lt_weights_", suffix=".json")
    os.close(fd)
    monkeypatch.setenv("LOLTRACK_WEIGHTS_PATH", path)
    monkeypatch.setenv("LOLTRACK_ADMIN", "1")
    g = r.get_weights()
    roles = g["data"]["roles"]
    roles["JUNGLE"]["Objectives"] += 0.1  # break sum
    res = r.put_weights({"roles": roles})
    assert res["ok"] is False
    assert res["error"]["code"] == "INVALID"


def test_weights_put_partial_rejected(monkeypatch):
    fd, path = tempfile.mkstemp(prefix="lt_weights_", suffix=".json")
    os.close(fd)
    monkeypatch.setenv("LOLTRACK_WEIGHTS_PATH", path)
    monkeypatch.setenv("LOLTRACK_ADMIN", "1")
    g = r.get_weights()
    roles = g["data"]["roles"]
    roles.pop("SUPPORT", None)
    res = r.put_weights({"roles": roles})
    assert res["ok"] is False
    assert res["error"]["message"].startswith("missing role")

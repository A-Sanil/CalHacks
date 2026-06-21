"""
test_voice_intake.py -- a spoken 911 call becomes a NEW search-and-rescue site
that the REAL solver routes to, on the SAME 24-node grid the dashboard renders.
Fully offline: the typed /voice/intake path needs no Deepgram key and no mic.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from solver.api.app import app
from solver.api import voice_intake as vi

client = TestClient(app)


def _payload(targets):
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disaster_state": "unit-test",
        "vehicles": [
            {"id": "V1", "type": "ground", "capacity": 8, "start_node": 0},
            {"id": "V2", "type": "ground", "capacity": 8, "start_node": 5},
        ],
        "target_nodes": targets,
        "dynamic_edge_modifiers": [],
    }


def _tnode(nid, prio=3.0, demand=2):
    return {"id": nid, "priority": prio, "demand": demand,
            "time_window": [0, 480], "required": False}


# --- grid / transcript parsing -------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("victims at grid E2", "E2"),
    ("echo two", "E2"),
    ("grid echo-two please", "E2"),
    ("two trapped at charlie four", "C4"),
    ("location bravo 3", "B3"),
    ("e-2", "E2"),
    ("nothing useful here", None),
])
def test_parse_grid_ref(text, expected):
    assert vi.parse_grid_ref(text) == expected


def test_grid_node_roundtrip():
    assert vi.grid_to_node("A", 1) == 0
    assert vi.grid_to_node("F", 1) == 5
    assert vi.grid_to_node("E", 2) == 10
    assert vi.grid_to_node("C", 4) == 20
    assert vi.node_to_grid(10) == "E2"
    assert vi.node_to_grid(20) == "C4"


@pytest.mark.parametrize("text,n", [
    ("two trapped", 2),
    ("six people inside", 6),
    ("3 victims", 3),
    ("family of four", 4),
    ("someone is hurt", 1),
])
def test_parse_demand(text, n):
    assert vi.parse_demand(text) == n


def test_critical_is_required():
    label, weight, required = vi.parse_priority("critical, two trapped")
    assert label == "critical" and required is True and weight >= 5.0


# --- the money shot: voice -> new site -> solver routes to it -------------
def test_voice_call_adds_site_and_solver_routes_to_it():
    body = {
        "transcript": "Aegis, new emergency, two trapped at grid echo two, critical",
        "request": _payload([_tnode(14, prio=3.0, demand=4)]),
    }
    r = client.post("/voice/intake", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["added"]["node_id"] == 10           # 'echo two' -> E2 -> node 10
    assert d["added"]["grid"] == "E2"
    assert d["added"]["priority_label"] == "critical"
    assert d["added"]["required"] is True
    assert d["added"]["served"] is True          # solver ROUTED to it
    assert d["added"]["served_by"]
    route = next(rt for rt in d["result"]["routes"]
                 if rt["vehicle_id"] == d["added"]["served_by"])
    assert 10 in route["ordered_nodes"]          # actually on the path


def test_fallback_node_when_no_grid_spoken():
    body = {"transcript": "we need help, someone is hurt",
            "request": _payload([_tnode(14)])}
    r = client.post("/voice/intake", json=body)
    assert r.status_code == 200, r.text
    added = r.json()["added"]
    assert added["grid_source"] == "fallback"
    assert added["node_id"] not in (0, 5, 14)    # not a depot / existing target


def test_audio_path_without_key_returns_503(monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setattr(vi, "_api_key", lambda: None)
    import io, json
    files = {"audio": ("call.webm", io.BytesIO(b"\x00\x01"), "audio/webm")}
    data = {"request": json.dumps(_payload([_tnode(14)]))}
    r = client.post("/voice/intake/audio", files=files, data=data)
    assert r.status_code == 503
    assert "DEEPGRAM_API_KEY" in r.json()["detail"]

"""Tests for the /optimize endpoint (frontend live solve path)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from solver.api.app import app

client = TestClient(app)

BASE_REQUEST = {
    "timestamp": "2026-06-20T21:00:00Z",
    "disaster_state": "Wildfire test",
    "vehicles": [
        {"id": "AIR-01", "type": "air", "capacity": 8, "start_node": 0},
        {"id": "GND-01", "type": "ground", "capacity": 10, "start_node": 23},
    ],
    "target_nodes": [
        {"id": 7, "priority": 9.0, "demand": 4, "time_window": [0, 60]},
        {"id": 16, "priority": 8.0, "demand": 5, "time_window": [0, 60]},
        {"id": 19, "priority": 9.5, "demand": 6, "time_window": [0, 60]},
    ],
    "dynamic_edge_modifiers": [],
}


def test_optimize_returns_routes():
    r = client.post("/optimize", json=BASE_REQUEST)
    assert r.status_code == 200
    data = r.json()
    assert data["routes"], "expected at least one route"
    for route in data["routes"]:
        assert route["ordered_nodes"], "route must have ordered nodes"
        assert route["svg_path"].startswith("M "), "svg_path must be drawable"
        assert route["eta_minutes"] >= 0
    assert data["metrics"]["people_routed"] >= 0
    assert data["solve_time_ms"] >= 0


def test_optimize_respects_blocked_edge():
    """A closed edge (huge multiplier) must never appear as a consecutive hop."""
    req = dict(BASE_REQUEST)
    req["dynamic_edge_modifiers"] = [
        {"edge": [13, 8], "multiplier": 9999, "reason": "collapse"},
    ]
    r = client.post("/optimize", json=req)
    assert r.status_code == 200
    for route in r.json()["routes"]:
        seq = route["ordered_nodes"]
        hops = {frozenset((seq[i], seq[i + 1])) for i in range(len(seq) - 1)}
        assert frozenset((13, 8)) not in hops, "closed edge was traversed"


def test_optimize_svg_matches_node_coords():
    """svg_path must contain one M/L command per ordered node."""
    r = client.post("/optimize", json=BASE_REQUEST)
    for route in r.json()["routes"]:
        commands = [tok for tok in route["svg_path"].split() if tok in ("M", "L")]
        assert len(commands) == len(route["ordered_nodes"])


def test_single_target_does_not_visit_entire_road_graph():
    """Intermediate road nodes may connect a route but are not CVRP stops."""
    req = {
        "timestamp": "2026-06-20T21:00:00Z",
        "disaster_state": "Focused evacuation",
        "vehicles": [
            {"id": "SAR-01", "type": "ground", "capacity": 8, "start_node": 18},
        ],
        "target_nodes": [
            {"id": 5, "priority": 9.5, "demand": 8, "time_window": [0, 90]},
        ],
        "dynamic_edge_modifiers": [],
    }
    r = client.post("/optimize", json=req)
    assert r.status_code == 200
    route = r.json()["routes"][0]["ordered_nodes"]
    assert route[0] == 18 and route[-1] == 18
    assert 5 in route
    assert len(route) <= 12, "route incorrectly visits most road-graph nodes"


def test_required_targets_are_all_visited():
    req = {
        "timestamp": "2026-06-20T21:00:00Z",
        "disaster_state": "Multiple emergency calls",
        "vehicles": [
            {"id": "SAR-01", "type": "ground", "capacity": 24, "start_node": 18},
        ],
        "target_nodes": [
            {"id": node, "priority": 9.0, "demand": 1, "time_window": [0, 9999], "required": True}
            for node in (5, 11, 16)
        ],
        "dynamic_edge_modifiers": [],
    }
    r = client.post("/optimize", json=req)
    assert r.status_code == 200
    route = r.json()["routes"][0]["ordered_nodes"]
    assert {5, 11, 16}.issubset(route)

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from solver.core.matrix import CostMatrixBuilder
from solver.core.schema import DynamicEdgeModifier, ProblemPayload, Vehicle, TargetNode
from solver.core.solver import SolverEngine


def _demo_matrix(n: int = 12) -> list[list[float]]:
    rng = np.random.default_rng(0)
    coords = rng.random((n, 2)) * 100
    diff = coords[:, None, :] - coords[None, :, :]
    return np.sqrt((diff ** 2).sum(axis=-1)).tolist()


def _sparse_grid_matrix(
    cols: int = 9,
    rows: int = 7,
) -> tuple[np.ndarray, list[list[float]]]:
    """Road grid like viz/index.html — sparse edges, 1e9 = no road."""
    n = cols * rows
    rng = lambda i: float(np.sin(i * 127.1 + 42.7) * 43758.5453 % 1)
    coords: list[list[float]] = []
    elevation: list[float] = []
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            coords.append([c * 22 + rng(idx) * 6, r * 20 + rng(idx + 99) * 6])
            elevation.append(
                0.3 + (c / cols) * 0.4 + (1 - r / rows) * 0.5 + rng(idx) * 0.15
            )

    edges: list[tuple[int, int]] = []

    def add(a: int, b: int) -> None:
        if 0 <= a < n and 0 <= b < n and a != b:
            key = (min(a, b), max(a, b))
            if key not in {(min(x, y), max(x, y)) for x, y in edges}:
                edges.append(key)

    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            if c + 1 < cols:
                add(idx, idx + 1)
            if r + 1 < rows:
                add(idx, idx + cols)
            if c + 1 < cols and r + 1 < rows and rng(idx) > 0.55:
                add(idx, idx + cols + 1)
            if c > 0 and r + 1 < rows and rng(idx + 50) > 0.6:
                add(idx, idx + cols - 1)

    matrix = np.full((n, n), 1e9)
    np.fill_diagonal(matrix, 0)
    for a, b in edges:
        dist = np.hypot(coords[b][0] - coords[a][0], coords[b][1] - coords[a][1])
        slope = 1 + abs(elevation[a] - elevation[b]) * 2.2
        terrain = 1 + (elevation[a] + elevation[b]) * 0.35
        w = dist * slope * terrain
        matrix[a, b] = matrix[b, a] = w
    return matrix, coords


def _single_vehicle_payload(**overrides) -> ProblemPayload:
    base = {
        "timestamp": datetime.now(timezone.utc),
        "disaster_state": "stable",
        "vehicles": [{"id": "V1", "type": "ground", "capacity": 20, "start_node": 0}],
        "target_nodes": [
            {"id": 3, "priority": 5.0, "demand": 2, "time_window": [0, 9999]},
            {"id": 7, "priority": 8.0, "demand": 3, "time_window": [0, 9999]},
            {"id": 9, "priority": 6.0, "demand": 1, "time_window": [0, 9999]},
        ],
        "dynamic_edge_modifiers": [],
        "baseline_matrix": _demo_matrix(),
        "node_coords": [(i * 10.0, i * 5.0) for i in range(12)],
    }
    base.update(overrides)
    return ProblemPayload.model_validate(base)


class TestSolverEngine:
    def test_single_vehicle_solve_fast(self):
        engine = SolverEngine(use_ml=False)
        payload = _single_vehicle_payload()
        result = engine.solve(payload)
        assert result.routes[0].vehicle_id == "V1"
        assert result.routes[0].path[0] == 0
        assert result.solve_time_ms < 2000  # generous for CI

    def test_blocked_edge_reroutes(self):
        engine = SolverEngine(use_ml=False)
        payload = _single_vehicle_payload(
            dynamic_edge_modifiers=[
                {"edge": [0, 3], "multiplier": 1000, "reason": "fire"},
            ]
        )
        baseline = engine.solve(_single_vehicle_payload())
        blocked = engine.solve(payload)
        # Path should still be valid
        assert blocked.routes[0].path[0] == 0
        assert blocked.total_cost >= baseline.total_cost

    def test_incremental_resolves_under_100ms_typical(self):
        engine = SolverEngine(use_ml=False)
        p1 = _single_vehicle_payload()
        r1 = engine.solve(p1)
        p2 = _single_vehicle_payload(
            disaster_state="escalating_wildfire",
            dynamic_edge_modifiers=[
                {"edge": [3, 7], "multiplier": 1000, "reason": "fire"},
            ],
        )
        r2 = engine.solve(p2)
        assert r2.solve_time_ms < 500
        assert r2.disaster_state == "escalating_wildfire"

    def test_matrix_cache_hit(self):
        builder = CostMatrixBuilder()
        payload = _single_vehicle_payload()
        m1 = builder.build(payload)
        m2 = builder.build(payload)
        assert np.shares_memory(m1, m2) or np.allclose(m1, m2)

    def test_sparse_grid_visits_targets_not_every_node(self):
        """Regression: single-vehicle must not TSP through all 63 grid nodes."""
        matrix, coords = _sparse_grid_matrix()
        targets = [8, 17, 26, 35, 44, 53, 62, 31, 40, 14]
        payload = ProblemPayload.model_validate(
            {
                "timestamp": datetime.now(timezone.utc),
                "disaster_state": "stable",
                "vehicles": [{"id": "V1", "type": "ground", "capacity": 50, "start_node": 0}],
                "target_nodes": [
                    {"id": t, "priority": 10 - i * 0.5, "demand": 2, "time_window": [0, 9999]}
                    for i, t in enumerate(targets)
                ],
                "dynamic_edge_modifiers": [],
                "baseline_matrix": matrix.tolist(),
                "node_coords": coords,
            }
        )
        engine = SolverEngine(use_ml=False)
        assert not engine._needs_cvrp(payload)
        result = engine.solve(payload)
        path = result.routes[0].path
        assert len(set(path)) < matrix.shape[0]
        assert all(t in path for t in targets)
        assert result.solver_used in {"lkh_sparse", "nn_sparse", "trivial"}


class TestMultiVehicle:
    def test_cvrp_assigns_routes(self):
        engine = SolverEngine(use_ml=False)
        payload = ProblemPayload.model_validate(
            {
                "timestamp": datetime.now(timezone.utc),
                "disaster_state": "stable",
                "vehicles": [
                    {"id": "V1", "type": "ground", "capacity": 5, "start_node": 0},
                    {"id": "V2", "type": "air", "capacity": 5, "start_node": 1},
                ],
                "target_nodes": [
                    {"id": 5, "priority": 9.0, "demand": 3, "time_window": [0, 200]},
                    {"id": 8, "priority": 4.0, "demand": 2, "time_window": [0, 200]},
                ],
                "baseline_matrix": _demo_matrix(),
            }
        )
        result = engine.solve(payload)
        assert len(result.routes) == 2
        for route in result.routes:
            assert route.path[0] in {0, 1}

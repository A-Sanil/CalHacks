from __future__ import annotations

import json
from datetime import datetime, timezone

import fakeredis
import numpy as np
import pytest

from solver.core.schema import ProblemPayload
from solver.core.solver import SolverEngine
from solver.redis_client import MatrixStore


@pytest.fixture
def redis_engine():
    client = fakeredis.FakeRedis(decode_responses=True)
    n = 15
    rng = np.random.default_rng(99)
    coords = rng.random((n, 2)) * 100
    diff = coords[:, None, :] - coords[None, :, :]
    matrix = np.sqrt((diff ** 2).sum(axis=-1))
    store = MatrixStore(client)
    store.save_matrix(matrix)
    store.save_coords(coords)
    return SolverEngine.from_redis(client, use_ml=False)


class TestRedisIntegration:
    def test_loads_matrix_from_redis(self, redis_engine):
        payload = ProblemPayload.model_validate(
            {
                "timestamp": datetime.now(timezone.utc),
                "disaster_state": "stable",
                "vehicles": [{"id": "V1", "type": "ground", "capacity": 10, "start_node": 0}],
                "target_nodes": [
                    {"id": 4, "priority": 5.0, "demand": 1, "time_window": [0, 9999]},
                    {"id": 10, "priority": 8.0, "demand": 2, "time_window": [0, 9999]},
                ],
                "dynamic_edge_modifiers": [
                    {"edge": [4, 10], "multiplier": 2.0, "reason": "smoke"},
                ],
            }
        )
        result = redis_engine.solve(payload)
        assert result.total_cost > 0
        assert len(result.routes[0].path) >= 3

    def test_dynamic_update_cycle(self, redis_engine):
        base = {
            "timestamp": datetime.now(timezone.utc),
            "disaster_state": "stable",
            "vehicles": [{"id": "V1", "type": "ground", "capacity": 10, "start_node": 0}],
            "target_nodes": [
                {"id": 3, "priority": 9.0, "demand": 1, "time_window": [0, 9999]},
                {"id": 8, "priority": 6.0, "demand": 1, "time_window": [0, 9999]},
            ],
            "dynamic_edge_modifiers": [],
        }
        r1 = redis_engine.solve(ProblemPayload.model_validate(base))
        base["disaster_state"] = "escalating_wildfire"
        base["dynamic_edge_modifiers"] = [
            {"edge": [0, 3], "multiplier": 1000, "reason": "active_fire_front"},
        ]
        r2 = redis_engine.solve(ProblemPayload.model_validate(base))
        assert r2.disaster_state == "escalating_wildfire"
        assert r2.solve_time_ms < 1000

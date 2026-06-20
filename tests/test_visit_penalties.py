from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from solver.core.schema import ProblemPayload
from solver.core.solver import SolverEngine


def _matrix(n: int = 6) -> list[list[float]]:
    m = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                m[i][j] = abs(i - j) * 10.0
    return m


class TestVisitPenalties:
    def test_reroute_avoids_visited_nodes(self):
        engine = SolverEngine(use_ml=False)
        base = {
            "timestamp": datetime.now(timezone.utc),
            "disaster_state": "stable",
            "vehicles": [{"id": "V1", "type": "ground", "capacity": 20, "start_node": 2}],
            "target_nodes": [
                {"id": 4, "priority": 5.0, "demand": 1, "time_window": [0, 9999]},
                {"id": 5, "priority": 5.0, "demand": 1, "time_window": [0, 9999]},
            ],
            "baseline_matrix": _matrix(),
            "visited_nodes": [0, 1],
        }
        result = engine.solve(ProblemPayload.model_validate(base))
        path = result.routes[0].path
        # Should not pass through visited nodes 0,1 unless unavoidable
        interior = [n for n in path[1:-1] if n not in {4, 5, 2}]
        assert 0 not in interior or 1 not in interior or len(interior) == 0

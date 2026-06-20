from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from solver.algorithms.nearest_neighbor import nearest_neighbor_tour, tour_cost
from solver.algorithms.two_opt import two_opt_improve
from solver.algorithms.tsp_lkh import solve_symmetric_tsp_lkh
from solver.core.matrix import apply_edge_modifiers
from solver.core.schema import DynamicEdgeModifier


def euclidean_matrix(n: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    coords = rng.random((n, 2))
    diff = coords[:, None, :] - coords[None, :, :]
    return np.sqrt((diff ** 2).sum(axis=-1))


class TestNearestNeighbor:
    def test_visits_all_nodes(self):
        matrix = euclidean_matrix(8)
        tour = nearest_neighbor_tour(matrix, start=0, nodes=list(range(1, 8)))
        assert set(tour) == set(range(8))
        assert tour[0] == 0
        assert tour[-1] == 0

    def test_empty_nodes(self):
        matrix = euclidean_matrix(4)
        tour = nearest_neighbor_tour(matrix, 0, [])
        assert tour == [0, 0]


class TestTwoOpt:
    def test_improves_or_equal_nn(self):
        matrix = euclidean_matrix(15, seed=1)
        nn = nearest_neighbor_tour(matrix, 0, list(range(1, 15)))
        improved = two_opt_improve(matrix, nn)
        assert tour_cost(matrix, improved) <= tour_cost(matrix, nn) + 1e-9

    def test_two_opt_beats_random_on_small_instance(self):
        matrix = euclidean_matrix(10, seed=2)
        random_tour = list(range(10)) + [0]
        improved = two_opt_improve(matrix, random_tour)
        assert tour_cost(matrix, improved) <= tour_cost(matrix, random_tour)


class TestLKH:
    def test_symmetric_tsp_returns_valid_tour(self):
        matrix = euclidean_matrix(12, seed=3)
        nodes = list(range(12))
        path, cost, solver = solve_symmetric_tsp_lkh(matrix, nodes, start=0)
        assert path[0] == 0
        assert path[-1] == 0
        assert cost == pytest.approx(tour_cost(matrix, path), rel=1e-6)
        assert solver in {"lkh", "nn_2opt", "trivial"}

    def test_lkh_produces_valid_tour(self):
        """LKH/2-opt returns a closed valid tour."""
        matrix = euclidean_matrix(10, seed=4)
        path, cost, _ = solve_symmetric_tsp_lkh(matrix, list(range(10)), start=0)
        assert path[0] == 0 and path[-1] == 0
        assert cost == pytest.approx(tour_cost(matrix, path), rel=1e-5)
        assert len(set(path[:-1])) == 10


class TestEdgeModifiers:
    def test_multiplier_applied_symmetrically(self):
        baseline = np.ones((5, 5)) * 10
        np.fill_diagonal(baseline, 0)
        mods = [DynamicEdgeModifier(edge=(1, 3), multiplier=2.0, reason="smoke")]
        modified = apply_edge_modifiers(baseline, mods)
        assert modified[1, 3] == 20
        assert modified[3, 1] == 20

    def test_block_edge_uses_blocked_cost(self):
        baseline = np.ones((4, 4)) * 5
        np.fill_diagonal(baseline, 0)
        mods = [DynamicEdgeModifier(edge=(0, 2), multiplier=1000, reason="fire")]
        modified = apply_edge_modifiers(baseline, mods, blocked_cost=1e9)
        assert modified[0, 2] >= 1e8

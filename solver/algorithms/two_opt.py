from __future__ import annotations

import numpy as np

from solver.algorithms.nearest_neighbor import tour_cost


def _delta_swap(matrix: np.ndarray, tour: list[int], i: int, k: int) -> float:
    """Cost change for reversing tour[i:k+1] (2-opt segment reversal)."""
    a, b = tour[i - 1], tour[i]
    c, d = tour[k], tour[(k + 1) % len(tour)] if k + 1 < len(tour) else tour[0]
    removed = matrix[a, b] + matrix[c, d]
    added = matrix[a, c] + matrix[b, d]
    return added - removed


def two_opt_improve(
    matrix: np.ndarray,
    tour: list[int],
    *,
    max_iterations: int = 2000,
    fixed_start: bool = True,
) -> list[int]:
    """Classic 2-opt local search. Tour may include closing return to depot."""
    if len(tour) < 4:
        return tour[:]

    best = tour[:]
    n = len(best)
    improved = True
    iterations = 0

    start_i = 1 if fixed_start else 0
    end_i = n - 1 if fixed_start and best[0] == best[-1] else n - 2

    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        for i in range(start_i, end_i):
            for k in range(i + 1, end_i + 1):
                if k - i == 1:
                    continue
                delta = _delta_swap(matrix, best, i, k)
                if delta < -1e-9:
                    best[i : k + 1] = reversed(best[i : k + 1])
                    improved = True
                    break
            if improved:
                break

    return best


def two_opt_cost(matrix: np.ndarray, tour: list[int], **kwargs) -> float:
    return tour_cost(matrix, two_opt_improve(matrix, tour, **kwargs))

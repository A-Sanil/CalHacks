from __future__ import annotations

import numpy as np


def tour_cost(matrix: np.ndarray, tour: list[int]) -> float:
    if len(tour) < 2:
        return 0.0
    total = 0.0
    for a, b in zip(tour, tour[1:]):
        total += matrix[a, b]
    return float(total)


def nearest_neighbor_tour(
    matrix: np.ndarray,
    start: int,
    nodes: list[int],
    *,
    return_to_start: bool = True,
) -> list[int]:
    """Greedy NN tour over `nodes` beginning at `start`."""
    if not nodes:
        return [start, start] if return_to_start else [start]

    remaining = set(nodes)
    tour = [start]
    current = start

    while remaining:
        nxt = min(remaining, key=lambda node: matrix[current, node])
        remaining.remove(nxt)
        tour.append(nxt)
        current = nxt

    if return_to_start and tour[-1] != start:
        tour.append(start)

    return tour

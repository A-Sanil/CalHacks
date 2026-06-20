from __future__ import annotations

import numpy as np

from solver.algorithms.nearest_neighbor import nearest_neighbor_tour, tour_cost
from solver.algorithms.two_opt import two_opt_improve
from solver.config import settings


def solve_symmetric_tsp_lkh(
    matrix: np.ndarray,
    nodes: list[int],
    *,
    start: int | None = None,
    return_to_start: bool = True,
) -> tuple[list[int], float, str]:
    """
    Solve symmetric TSP on `nodes` using LKH (via elkai) with NN+2-opt fallback.
    """
    if len(nodes) <= 1:
        depot = start if start is not None else (nodes[0] if nodes else 0)
        path = [depot]
        if return_to_start and len(path) == 1:
            path = [depot, depot]
        return path, 0.0, "trivial"

    depot = start if start is not None else nodes[0]
    visit_nodes = [n for n in nodes if n != depot]
    if not visit_nodes:
        path = [depot, depot] if return_to_start else [depot]
        return path, 0.0, "trivial"

    # Submatrix indices: depot first, then visit nodes
    index_map = [depot] + visit_nodes
    sub = matrix[np.ix_(index_map, index_map)]

    try:
        import elkai

        tour_indices = elkai.DistanceMatrix(sub.tolist()).solve_tsp(runs=10)
        path = [index_map[i] for i in tour_indices]
        # Rotate so tour starts at depot for consistent downstream use
        if depot in path:
            idx = path.index(depot)
            path = path[idx:] + path[:idx]
        if return_to_start and path and path[-1] != path[0]:
            path.append(path[0])
        # LKH output + short 2-opt polish beats raw LKH on small instances
        path = two_opt_improve(matrix, path, max_iterations=2000)
        cost = tour_cost(matrix, path)
        return path, cost, "lkh"
    except Exception:
        pass

    nn = nearest_neighbor_tour(matrix, depot, visit_nodes, return_to_start=return_to_start)
    improved = two_opt_improve(matrix, nn, max_iterations=5000)
    cost = tour_cost(matrix, improved)
    return improved, cost, "nn_2opt"

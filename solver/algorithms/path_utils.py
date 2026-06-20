from __future__ import annotations

import heapq

import numpy as np


def dijkstra(
    matrix: np.ndarray,
    source: int,
    target: int,
) -> tuple[float, list[int]]:
    """Shortest path on sparse matrix (1e9 = no edge)."""
    n = matrix.shape[0]
    dist = {source: 0.0}
    prev: dict[int, int | None] = {source: None}
    heap: list[tuple[float, int]] = [(0.0, source)]

    while heap:
        d, u = heapq.heappop(heap)
        if u == target:
            break
        if d > dist.get(u, float("inf")):
            continue
        for v in range(n):
            w = matrix[u, v]
            if w >= 1e8:
                continue
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    if target not in dist:
        return float("inf"), [source, target]

    path: list[int] = []
    at: int | None = target
    while at is not None:
        path.append(at)
        at = prev.get(at)
    path.reverse()
    return dist[target], path


def expand_tour(matrix: np.ndarray, tour: list[int]) -> list[int]:
    """Expand a node tour to include intermediate road nodes."""
    if len(tour) <= 1:
        return tour
    full: list[int] = [tour[0]]
    for i in range(len(tour) - 1):
        _, leg = dijkstra(matrix, tour[i], tour[i + 1])
        if leg[0] != full[-1]:
            full.extend(leg)
        else:
            full.extend(leg[1:])
    return full


def collapse_path(path: list[int]) -> list[int]:
    if not path:
        return path
    out = [path[0]]
    for node in path[1:]:
        if node != out[-1]:
            out.append(node)
    return out


def solve_sparse_tsp(
    matrix: np.ndarray,
    start: int,
    targets: list[int],
) -> tuple[list[int], float, str]:
    """TSP over targets using shortest-path distances on a sparse road network."""
    visit = [start] + [t for t in targets if t != start]
    if len(visit) <= 1:
        return [start, start], 0.0, "trivial"

    condensed = condensed_distances(matrix, visit)

    try:
        import elkai

        tour_idx = elkai.DistanceMatrix(condensed.tolist()).solve_tsp(runs=10)
        tour = [visit[i] for i in tour_idx]
        if start in tour:
            idx = tour.index(start)
            tour = tour[idx:] + tour[:idx]
        if tour[-1] != start:
            tour.append(start)
        tour = collapse_path(tour)
        full = expand_tour(matrix, tour)
        cost = sum(
            matrix[full[i], full[i + 1]]
            for i in range(len(full) - 1)
            if matrix[full[i], full[i + 1]] < 1e8
        )
        return full, float(cost), "lkh_sparse"
    except Exception:
        pass

    # Fallback: nearest neighbor on condensed metric
    remaining = set(targets)
    order = [start]
    cur = start
    while remaining:
        nxt = min(
            remaining,
            key=lambda t: condensed[visit.index(cur), visit.index(t)],
        )
        remaining.remove(nxt)
        order.append(nxt)
        cur = nxt
    order.append(start)
    full = expand_tour(matrix, collapse_path(order))
    cost = sum(matrix[full[i], full[i + 1]] for i in range(len(full) - 1) if matrix[full[i], full[i + 1]] < 1e8)
    return full, float(cost), "nn_sparse"


def condensed_distances(matrix: np.ndarray, nodes: list[int]) -> np.ndarray:
    """All-pairs shortest path costs between `nodes`."""
    k = len(nodes)
    out = np.zeros((k, k))
    for i, a in enumerate(nodes):
        for j, b in enumerate(nodes):
            if i == j:
                continue
            cost, _ = dijkstra(matrix, a, b)
            out[i, j] = cost
    return out

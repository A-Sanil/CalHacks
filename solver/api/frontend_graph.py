"""
frontend_graph.py  --  24-node tactical grid mirrored from
frontend/src/simulation/graph.ts so the backend /optimize endpoint solves on the
SAME map the dashboard renders. Edge weight = round(hypot(dx, dy) / 10), matching
the frontend distance() helper. Coordinates are SVG pixels (used for svg_path).
"""
from __future__ import annotations

import heapq
from math import hypot, inf

# node id -> (x, y) in SVG pixel space
NODE_XY: dict[int, tuple[int, int]] = {
    0: (72, 72),
    1: (178, 86),
    2: (282, 68),
    3: (386, 91),
    4: (495, 65),
    5: (620, 83),
    6: (90, 184),
    7: (190, 195),
    8: (300, 176),
    9: (402, 204),
    10: (510, 178),
    11: (628, 196),
    12: (68, 300),
    13: (178, 286),
    14: (288, 313),
    15: (395, 287),
    16: (505, 315),
    17: (630, 292),
    18: (82, 430),
    19: (190, 412),
    20: (300, 438),
    21: (410, 408),
    22: (518, 433),
    23: (625, 408),
}

# undirected road links (mirrors graph.ts links)
LINKS: list[tuple[int, int]] = [
    (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (6, 7), (7, 8), (8, 9),
    (9, 10), (10, 11), (12, 13), (13, 14), (14, 15), (15, 16), (16, 17), (18, 19),
    (19, 20), (20, 21), (21, 22), (22, 23), (0, 6), (6, 12), (12, 18), (1, 7),
    (7, 13), (13, 19), (2, 8), (8, 14), (14, 20), (3, 9), (9, 15), (15, 21),
    (4, 10), (10, 16), (16, 22), (5, 11), (11, 17), (17, 23), (18, 13), (13, 8),
    (8, 3), (19, 14), (14, 9), (9, 4), (20, 15), (15, 10), (10, 5), (12, 7),
    (7, 2), (21, 16), (16, 11),
]

N = len(NODE_XY)
BLOCK_THRESHOLD = 1000.0   # modifier multiplier >= this means the road is closed


def base_edges() -> dict[tuple[int, int], float]:
    edges: dict[tuple[int, int], float] = {}
    for a, b in LINKS:
        ax, ay = NODE_XY[a]
        bx, by = NODE_XY[b]
        w = float(round(hypot(ax - bx, ay - by) / 10))
        edges[(a, b)] = w
        edges[(b, a)] = w
    return edges


def live_adjacency(modifiers) -> dict[int, dict[int, float]]:
    """Apply dynamic_edge_modifiers: scale weight; drop edge if multiplier >= BLOCK_THRESHOLD."""
    mult: dict[tuple[int, int], float] = {}
    for mod in modifiers or []:
        edge = mod.get("edge") if isinstance(mod, dict) else getattr(mod, "edge", None)
        if not edge or len(edge) < 2:
            continue
        a, b = int(edge[0]), int(edge[1])
        if isinstance(mod, dict):
            f = float(mod.get("multiplier", 1.0))
        else:
            f = float(getattr(mod, "multiplier", 1.0))
        mult[(a, b)] = f
        mult[(b, a)] = f
    adj: dict[int, dict[int, float]] = {i: {} for i in range(N)}
    for (a, b), w in base_edges().items():
        f = mult.get((a, b), 1.0)
        if f >= BLOCK_THRESHOLD:
            continue
        adj[a][b] = w * f
    return adj


def _dijkstra(adj, src):
    dist = {src: 0.0}
    prev: dict[int, int] = {}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, inf):
            continue
        for v, w in adj[u].items():
            nd = d + w
            if nd < dist.get(v, inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def all_pairs(adj):
    dist = [[inf] * N for _ in range(N)]
    prevs: list[dict[int, int]] = [dict() for _ in range(N)]
    for s in range(N):
        d, prev = _dijkstra(adj, s)
        prevs[s] = prev
        dist[s][s] = 0.0
        for t, dd in d.items():
            dist[s][t] = dd
    return dist, prevs


def cost_matrix(adj, blocked_cost: float = 1e9):
    dist, _ = all_pairs(adj)
    return [[(blocked_cost if v == inf else round(v, 4)) for v in row] for row in dist]


def node_coords() -> list[list[float]]:
    return [[float(NODE_XY[i][0]), float(NODE_XY[i][1])] for i in range(N)]


def reconstruct(src: int, dst: int, prevs) -> list[int]:
    if src == dst:
        return [src]
    prev = prevs[src]
    if dst not in prev:
        return [src, dst]
    path = [dst]
    cur = dst
    while cur != src:
        cur = prev.get(cur)
        if cur is None:
            break
        path.append(cur)
    path.reverse()
    return path


def expand_waypoints(waypoints: list[int], prevs) -> list[int]:
    full: list[int] = []
    for i in range(len(waypoints) - 1):
        seg = reconstruct(waypoints[i], waypoints[i + 1], prevs)
        if i > 0:
            seg = seg[1:]
        full.extend(seg)
    if not full and waypoints:
        full = [waypoints[0]]
    return full


def svg_path(node_seq: list[int]) -> str:
    parts = []
    for i, nid in enumerate(node_seq):
        x, y = NODE_XY[nid]
        parts.append(("M " if i == 0 else "L ") + str(x) + " " + str(y))
    return " ".join(parts)

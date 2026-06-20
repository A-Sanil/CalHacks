"""
graph_traversal.py  --  GraphRAG localized sub-graph retrieval.

PDF: "Before formulating the routing problem, the Agent queries the GraphRAG to
retrieve the localized sub-graph of the affected area, ensuring it has complete
situational awareness of impassable non-Euclidean terrains."

This is the TRAVERSAL step. Given the nodes touched by active hazards, we do a
breadth-first k-hop expansion over the live graph in Redis and return the local
sub-graph (nodes + current edge states). The contract builder can then scope the
problem to this neighborhood instead of the whole map.
"""
from __future__ import annotations
from collections import deque
from redis_store import AegisStore


def neighbors(store: AegisStore, node: int) -> list[int]:
    """Out-neighbors of a node from the directed edge set in Redis."""
    return sorted(j for (i, j) in store.all_edges() if i == node)


def affected_centers(store: AegisStore) -> list[int]:
    """Nodes incident to any active hazard (multiplier != 1) -> traversal seeds."""
    centers = set()
    for m in store.active_modifiers():
        centers.update(m["edge"])
    return sorted(centers)


def localized_subgraph(store: AegisStore, centers: list[int], hops: int = 1) -> dict:
    """
    BFS k-hop expansion from the seed nodes.
    Returns {nodes:[...], edges:[{edge, base_cost, multiplier, final_cost, reason}]}.
    """
    visited = set(centers)
    frontier = deque((c, 0) for c in centers)
    while frontier:
        node, depth = frontier.popleft()
        if depth >= hops:
            continue
        for m in neighbors(store, node):
            if m not in visited:
                visited.add(m)
                frontier.append((m, depth + 1))
    edges = []
    for (i, j) in store.all_edges():
        if i in visited and j in visited:
            e = store.get_edge(i, j)
            edges.append({
                "edge": [i, j],
                "base_cost": float(e["base_cost"]),
                "multiplier": float(e["multiplier"]),
                "final_cost": store.get_final_cost(i, j),
                "reason": e["reason"],
            })
    return {"nodes": sorted(visited), "edges": edges}

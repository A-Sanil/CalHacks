"""
aegis_contract.py  --  bridge the Aegis JSON contract <-> the real SolverEngine.

Flow:
  Aegis contract (dict from contract_builder)            [vehicles, target_nodes, modifiers]
      -> build_live_matrix(store)                        [all-pairs shortest path on LIVE costs]
      -> ProblemPayload (solver/core/schema.py)
      -> SolverEngine.solve()                            [CVRP / TSP-LKH / 2-opt]
      -> SolveResponse
      -> Aegis solution dict                             [{vehicles:[{id,route,load,cost}], total_cost, dropped}]

Design note: the live edge multipliers (fire, flood, blockage) are baked into the
cost matrix via AegisStore.get_final_cost (= base x multiplier), then shortest paths
are computed, so a blocked road naturally reroutes. We therefore hand the solver an
already-live matrix and an EMPTY modifier list (avoids double-applying), while still
surfacing the human-readable modifiers in the returned solution for the dashboard.
"""
from __future__ import annotations

import heapq
from math import inf
from typing import Any

from solver.config import settings
from solver.core.schema import ProblemPayload
from solver.core.solver import SolverEngine


def build_live_matrix(store) -> tuple[list[int], list[list[float]], list[list[float]]]:
    """All-pairs shortest-path cost matrix on LIVE edge weights.

    Returns (node_ids, matrix, coords). Aegis node ids are contiguous 0..N-1, so the
    matrix is indexed directly by node id. coords[i] = [lng, lat] for the frontend map.
    """
    node_ids = sorted(int(n) for n in store.all_node_ids())
    n = len(node_ids)

    # live directed adjacency (base x multiplier)
    adj: dict[int, dict[int, float]] = {i: {} for i in node_ids}
    for (i, j) in store.all_edges():
        c = store.get_final_cost(i, j)
        if c is None:
            continue
        if j not in adj[i] or c < adj[i][j]:
            adj[i][j] = float(c)

    BIG = float(settings.blocked_cost)
    matrix = [[0.0 if i == j else BIG for j in range(n)] for i in range(n)]

    # Dijkstra from every source -> true metric for the VRP/TSP solver
    for src in node_ids:
        dist = {src: 0.0}
        pq: list[tuple[float, int]] = [(0.0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, inf):
                continue
            for v, w in adj[u].items():
                nd = d + w
                if nd < dist.get(v, inf):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        for dst, dd in dist.items():
            matrix[src][dst] = round(dd, 4)

    coords = [[0.0, 0.0] for _ in range(n)]
    for nid in node_ids:
        node = store.get_node(nid) or {}
        coords[nid] = [float(node.get("lng", 0.0) or 0.0), float(node.get("lat", 0.0) or 0.0)]

    return node_ids, matrix, coords


def contract_to_payload(contract: dict[str, Any], store) -> ProblemPayload:
    """Map the Aegis contract dict onto the solver's Pydantic ProblemPayload."""
    _node_ids, matrix, coords = build_live_matrix(store)
    return ProblemPayload(
        timestamp=contract.get("timestamp"),
        disaster_state=contract.get("disaster_state", "active"),
        vehicles=contract["vehicles"],
        target_nodes=contract.get("target_nodes", []),
        dynamic_edge_modifiers=[],          # live weights already baked into matrix
        baseline_matrix=matrix,
        node_coords=coords,
    )


def response_to_solution(response, contract: dict[str, Any]) -> dict[str, Any]:
    """Map the solver's SolveResponse back to the Aegis solution schema."""
    served: set[int] = set()
    vehicles_out: list[dict[str, Any]] = []
    for r in response.routes:
        path = [int(x) for x in r.path]
        depot = path[0] if path else None
        for nid in path:
            if nid != depot:
                served.add(nid)
        vehicles_out.append({
            "id": r.vehicle_id,
            "route": path,
            "load": int(r.demands_served),
            "cost": round(float(r.cost), 2),
            "priority_collected": round(float(r.priority_collected), 3),
        })

    target_ids = {int(t["id"]) for t in contract.get("target_nodes", [])}
    dropped = sorted(target_ids - served)

    # total_cost is the sum of the actual route costs (consistent with what the
    # dashboard renders); the raw CVRP/TSP objective is surfaced as solver_objective.
    total_cost = round(sum(v["cost"] for v in vehicles_out), 2)

    return {
        "vehicles": vehicles_out,
        "total_cost": total_cost,
        "solver_objective": round(float(response.total_cost), 2),
        "total_priority": round(float(response.total_priority), 3),
        "dropped": dropped,
        "solver_used": response.solver_used,
        "solve_time_ms": round(float(response.solve_time_ms), 2),
        "node_coords": response.metadata.get("node_coords"),
        "edge_modifiers": contract.get("dynamic_edge_modifiers", []),
        "disaster_state": contract.get("disaster_state"),
    }


def solve_contract(contract: dict[str, Any], store) -> dict[str, Any]:
    """One-shot: Aegis contract dict -> real solver -> Aegis solution dict."""
    payload = contract_to_payload(contract, store)
    engine = SolverEngine.from_redis(None)   # matrix supplied inline via baseline_matrix
    response = engine.solve(payload)
    return response_to_solution(response, contract)

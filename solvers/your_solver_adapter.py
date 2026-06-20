"""
your_solver_adapter.py  --  wrap your friend's solver so it plugs into Aegis.

solver_bridge calls:  adapter(contract, store) -> solution dict

Plug in with:
    from solver_bridge import run_solver
    from solvers.your_solver_adapter import adapter
    solution = run_solver(store, adapter)

You must return EXACTLY:
    {
      "vehicles": [{"id": str, "route": [node_id, ...], "load": int, "cost": float}, ...],
      "total_cost": float,
      "dropped": [node_id, ...],   # targets that could not be served
    }
"""
from __future__ import annotations
from redis_store import AegisStore

# ---- TODO(1): import your friend's solver -------------------------------------
# from their_module import solve_vrp


BIG = 1e6  # cost for a non-existent edge (keeps the matrix dense for VRP solvers)


def build_cost_matrix(contract: dict, store: AegisStore):
    """Every node referenced by the contract -> dense cost matrix via O(1) Redis lookups.

    Returns (node_ids, index_of, matrix) where matrix[index_of[a]][index_of[b]]
    is the LIVE cost (base x multiplier) of edge a->b, or BIG if there is no edge.
    """
    node_ids = sorted(
        {v["start_node"] for v in contract["vehicles"]}
        | {t["id"] for t in contract["target_nodes"]}
    )
    index_of = {n: k for k, n in enumerate(node_ids)}
    n = len(node_ids)
    matrix = [[0.0] * n for _ in range(n)]
    for a in node_ids:
        for b in node_ids:
            if a == b:
                continue
            c = store.get_final_cost(a, b)
            matrix[index_of[a]][index_of[b]] = c if c is not None else BIG
    return node_ids, index_of, matrix


def adapter(contract: dict, store: AegisStore) -> dict:
    node_ids, index_of, matrix = build_cost_matrix(contract, store)

    vehicles = contract["vehicles"]        # [{id, type, capacity, start_node}]
    targets  = contract["target_nodes"]    # [{id, priority, demand, time_window}]
    demands  = {t["id"]: t["demand"] for t in targets}

    # ---- TODO(2): call your friend's solver ----------------------------------
    # Translate the Aegis inputs into whatever shape their solver wants, e.g.:
    #   depots     = [index_of[v["start_node"]] for v in vehicles]
    #   capacities = [v["capacity"] for v in vehicles]
    #   node_demand= [demands.get(nid, 0) for nid in node_ids]
    #   priorities = {index_of[t["id"]]: t["priority"] for t in targets}
    #   raw = solve_vrp(matrix, depots, capacities, node_demand, priorities)
    raise NotImplementedError(
        "Plug your friend's solver in TODO(2), then map its output in TODO(3)."
    )

    # ---- TODO(3): map their output -> Aegis solution schema ------------------
    # 'raw.routes' below is illustrative -- adjust to your solver's real output.
    # out_vehicles = []
    # for v, route_idx in zip(vehicles, raw.routes):            # route_idx: list[int] into node_ids
    #     route = [node_ids[k] for k in route_idx]
    #     load  = sum(demands.get(nid, 0) for nid in route)
    #     cost  = sum(matrix[route_idx[i]][route_idx[i + 1]] for i in range(len(route_idx) - 1))
    #     out_vehicles.append({"id": v["id"], "route": route, "load": load, "cost": round(cost, 2)})
    # served  = {nid for ov in out_vehicles for nid in ov["route"]}
    # dropped = [t["id"] for t in targets if t["id"] not in served]
    # return {
    #     "vehicles": out_vehicles,
    #     "total_cost": round(sum(ov["cost"] for ov in out_vehicles), 2),
    #     "dropped": dropped,
    # }

"""
solver_bridge.py  --  FEATURE 3: close the loop. Read the contract from Redis,
run YOUR solver (inject any callable), write the solution back into Redis + publish.

  run_solver(store, solver_fn=None) -> solution dict
  solver_fn(contract, store) must return:
    {"vehicles":[{"id","route":[node_ids],"load","cost"}], "total_cost", "dropped":[node_ids]}

A capacity-aware greedy mock_solver is included ONLY so the loop is testable without
your real solver. Swap it out: run_solver(store, my_real_solver).
"""
from __future__ import annotations
from redis_store import AegisStore


def _hop_cost(store: AegisStore, a: int, b: int) -> float:
    c = store.get_final_cost(a, b)
    return c if c is not None else 50.0  # no direct edge -> expensive proxy


def mock_solver(contract: dict, store: AegisStore) -> dict:
    vehicles = [dict(v, route=[v["start_node"]], load=0, cost=0.0) for v in contract["vehicles"]]
    targets = sorted(contract["target_nodes"], key=lambda t: -t["priority"])
    dropped = []
    for t in targets:
        placed = False
        for v in sorted(vehicles, key=lambda x: x["cost"]):
            if v["load"] + t["demand"] <= v["capacity"]:
                last = v["route"][-1]
                v["cost"] += _hop_cost(store, last, t["id"])
                v["route"].append(t["id"])
                v["load"] += t["demand"]
                placed = True
                break
        if not placed:
            dropped.append(t["id"])
    return {
        "vehicles": [{"id": v["id"], "route": v["route"], "load": v["load"], "cost": round(v["cost"], 2)} for v in vehicles],
        "total_cost": round(sum(v["cost"] for v in vehicles), 2),
        "dropped": dropped,
    }


def run_solver(store: AegisStore, solver_fn=None) -> dict:
    contract = store.get_contract()
    if contract is None:
        raise RuntimeError("no contract in redis; build one first")
    fn = solver_fn or mock_solver
    solution = fn(contract, store)
    store.store_solution(solution)   # write back + PUBLISH aegis:routes:update
    return solution

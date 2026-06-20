# Integrating your solver

Aegis decouples **state** (Redis, O(1) live edge/node updates) from **solving**
(on demand). Your friend's solver only has to speak one small contract.

## The seam

`solver_bridge.run_solver(store, solver_fn)` does three things:
1. reads the contract from Redis (`aegis:contract:latest`),
2. calls `solver_fn(contract, store)`,
3. writes the returned solution back to Redis (`aegis:routes:latest`) **and**
   publishes `aegis:routes:update` for the dashboard.

So your only job is to provide `solver_fn(contract, store) -> solution`.

## Input: the contract

```python
{
  "timestamp": float,
  "disaster_state": "escalating_wildfire",
  "vehicles": [
    {"id": "V1", "type": "air_evac", "capacity": 4, "start_node": 0}
  ],
  "target_nodes": [
    {"id": 7, "priority": 0.92, "demand": 3, "time_window": [0, 30]}
  ],
  "dynamic_edge_modifiers": [
    {"edge": [2, 3], "multiplier": 4.0, "reason": "fire jumped Hwy 9 bridge"}
  ]
}
```

## Live edge weights (the whole point of Redis)

Never hard-code distances. Ask Redis for the **current** cost:

```python
cost = store.get_final_cost(i, j)   # base_cost * live multiplier, or None if no edge
```

The helper `solvers/your_solver_adapter.build_cost_matrix(contract, store)` turns
all contract nodes into a dense matrix for VRP-style solvers in one call.

## Output: the solution (return EXACTLY this)

```python
{
  "vehicles": [
    {"id": "V1", "route": [0, 7, 3], "load": 3, "cost": 12.5}
  ],
  "total_cost": 12.5,
  "dropped": [9]          # target ids you could not serve
}
```

## Wire it up

```python
from solver_bridge import run_solver
from solvers.your_solver_adapter import adapter
solution = run_solver(store, adapter)
```

Fill the three `TODO` blocks in `solvers/your_solver_adapter.py`:
1. import the solver, 2. call it, 3. map its output to the schema above.

A capacity-aware greedy `mock_solver` already lives in `solver_bridge.py` so the
loop is testable before the real solver lands.

# Agentic Optimization Engine — Solver

Real-time combinatorial solver for the AOE pipeline. Accepts the LLM-produced JSON matrix payload (Step B), applies dynamic edge modifiers to the Redis baseline graph (Step C), and returns optimal vehicle routes in milliseconds.

## Architecture

```
LLM Agent (Step A/B)          GraphRAG / Telemetry
        │                              │
        ▼                              ▼
   POST /solve  ◄──── baseline matrix ──── Redis
        │
        ├──► CostMatrixBuilder (modifiers + cache)
        ├──► TSP: LKH (elkai) → NN + 2-opt fallback
        ├──► CVRP: OR-Tools (multi-vehicle, capacity, time windows)
        ├──► ML warm-start (optional, PyTorch pointer net)
        │
        ▼
   SolveResponse + WebSocket `route_update` ──► Mapbox Dashboard
```

## Quick Start

```bash
pip install -e ".[dev]"

# Seed Redis (optional — pass baseline_matrix inline for tests)
python scripts/seed_redis.py --nodes 20

# Start solver API
python -m solver.api.app

# Run tests
pytest -v

# Train ML warm-start model (optional, ~30s)
python -c "from solver.algorithms.ml_warmstart import train_warmstart_model; train_warmstart_model()"

# Simulate dynamic re-routing
python scripts/simulate_dynamic_routes.py

# Open viz/index.html in browser (connects to ws://localhost:8000/ws/routes)
```

## JSON Contract (Input)

Matches the architecture spec:

```json
{
  "timestamp": "2026-06-20T12:04:00Z",
  "disaster_state": "escalating_wildfire",
  "vehicles": [{"id": "V1", "type": "ground_heavy", "capacity": 12, "start_node": 0}],
  "target_nodes": [{"id": 5, "priority": 9.5, "demand": 3, "time_window": [0, 45]}],
  "dynamic_edge_modifiers": [{"edge": [3, 5], "multiplier": 1000, "reason": "active_fire_front"}]
}
```

For offline/dev, include `"baseline_matrix"` and `"node_coords"` inline.

## Output / Dashboard Integration

`POST /solve` returns routes and broadcasts this WebSocket event:

```json
{
  "type": "route_update",
  "timestamp": "...",
  "disaster_state": "escalating_wildfire",
  "solve_time_ms": 12.4,
  "solver_used": "lkh",
  "vehicles": [{"id": "V1", "path": [0, 5, 8, 0], "cost": 142.3, "priority_collected": 13.5}],
  "edge_modifiers_applied": [...]
}
```

Your friend's Mapbox dashboard should subscribe to `ws://<host>:8000/ws/routes` or POST to `/solve` and listen for broadcasts. The viz in `viz/index.html` is a minimal reference implementation.

## Performance

- Modified matrix LRU cache (32 entries) for rapid re-solve on edge updates
- Previous-route warm-start for OR-Tools CVRP
- ML pointer network warm-start + 2-opt for dynamic TSP re-routing
- Single-vehicle symmetric TSP uses **LKH** via `elkai`; falls back to NN+2-opt

Target: **<100ms** re-solve on ~20 node instances (typical hackathon demo scale).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AOE_REDIS_URL` | `redis://localhost:6379/0` | Baseline matrix store |
| `AOE_MATRIX_KEY` | `aoe:distance_matrix` | Redis key |
| `AOE_USE_ML_WARMSTART` | `true` | Enable ML warm-start |
| `AOE_LKH_TIME_LIMIT_MS` | `500` | OR-Tools time limit |

## Integration Points

| Component | Interface |
|-----------|-----------|
| LLM Agent | `POST /solve` with JSON payload |
| Redis / OSM graph | `aoe:distance_matrix`, `aoe:node_coords` |
| Dashboard | WebSocket `/ws/routes`, event type `route_update` |
| Crisis injection | Send updated payload with new `dynamic_edge_modifiers` |

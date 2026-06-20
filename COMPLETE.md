# Aegis Route — Full-Stack Integration (`complete` branch)

Real-time wildfire **search-and-rescue route optimization**: a React tactical
dashboard talks to a FastAPI backend that runs a **real OR-Tools CVRP solver**
over a live, Redis-backed graph whose edge weights are updated from unstructured
field intel (911 calls, fire dept, weather, social) via a GraphRAG + LLM agent.

This document describes the **end-to-end wiring** completed on the `complete`
branch: `frontend  ->  /optimize  ->  SolverEngine  ->  routes  ->  map`.

---

## 1. Architecture at a glance

```
                      unstructured intel (911, fire dept, weather, social)
                                       |
                          extractor_agent (LLM + rule fallback)
                                       |
   GraphRAG static graph  ---->  Redis live state (O(1) edge weights, priorities)
                                       |
                              contract_builder  ->  Matrix Payload JSON
                                       |
 React dashboard  --POST /optimize-->  FastAPI (solver/api/app.py)
   (frontend/)                          |
        ^                       frontend_graph.py  (24-node grid, live matrix)
        |                               |
        |                       SolverEngine  (OR-Tools CVRP + 2-opt + ML warm-start)
        |                               |
        +------- OptimizationResult ----+   routes[] {ordered_nodes, svg_path, eta, priority}
                 (routes drawn on the tactical map)
```

- **GraphRAG** = static, pre-indexed knowledge graph (roads/terrain).
- **Redis** = live state layer (real-time edge multipliers, node priorities).
- **Solver** = on-demand OR-Tools CVRP with priority-aware triage.
- **Frontend** = Vite/React tactical map + incident feed + ops sidebar.

---

## 2. What the integration added

| File | Purpose |
|------|---------|
| `solver/api/frontend_graph.py` | Backend mirror of the frontend's 24-node grid. Edge weight = `round(hypot(dx,dy)/10)`. Applies `dynamic_edge_modifiers` (closed roads = multiplier >= 1000), builds the all-pairs cost matrix, and reconstructs full road paths for drawing. |
| `solver/api/optimize.py` | New **`POST /optimize`** endpoint. Accepts the frontend `OptimizationRequest`, bakes live edge modifiers into the matrix, runs the **real `SolverEngine`**, and returns `OptimizationResult` with `ordered_nodes` + `svg_path` drawn on the same grid the map renders. |
| `frontend/src/services/solver.ts` | Rewritten client. `buildRequestFromScenario()` turns a hazard scenario (blocked edges + penalties) into a solver contract; `optimizeRoute()` POSTs to the backend and **falls back gracefully** to an offline result if the API is down. |
| `frontend/src/components/TacticalMap.tsx` | Now renders the **real solver routes** (one colour per vehicle, with a live legend) on top of the local Dijkstra preview. Footer shows `SOLVER: LIVE / OFFLINE`. |
| `frontend/src/App.tsx` | Each simulation now (1) shows an instant local preview, then (2) calls the live backend solver and overlays its routes + real metrics in the feed and status strip. |
| `tests/test_optimize_endpoint.py` | 3 new tests: returns routes, respects blocked edges, svg_path matches node count. |

---

## 3. Data contract

**Request — `OptimizationRequest`** (frontend -> backend):
```json
{
  "timestamp": "2026-06-20T21:00:00Z",
  "disaster_state": "Wildfire - diagonal corridor closed",
  "vehicles":  [{ "id": "AIR-01", "type": "air_rescue", "capacity": 8, "start_node": 0 }],
  "target_nodes": [{ "id": 7, "priority": 9.0, "demand": 4, "time_window": [0, 45] }],
  "dynamic_edge_modifiers": [{ "edge": [13, 8], "multiplier": 9999, "reason": "collapse" }]
}
```

**Response — `OptimizationResult`** (backend -> frontend):
```json
{
  "generated_at": "2026-06-20T21:00:00Z",
  "solve_time_ms": 515.24,
  "routes": [
    { "vehicle_id": "AIR-01", "ordered_nodes": [0,6,12,13,7,8,...],
      "svg_path": "M 72 72 L ...", "eta_minutes": 115.0, "priority_served": 15.0 }
  ],
  "metrics": { "people_routed": 23, "total_priority_served": 45.5 }
}
```

A closed road (`multiplier >= 1000`) is removed from the graph, so it never
appears as a consecutive hop in any `ordered_nodes` — verified by tests and by
the live run (AIR-01 detours `13 -> 7 -> 8` instead of the closed `13 -> 8`).

---

## 4. How to run

### Backend (FastAPI solver) — http://localhost:8000
```powershell
# Windows
./scripts/run_backend.ps1
# macOS / Linux
./scripts/run_backend.sh
```

### Frontend (React dashboard) — http://localhost:5173
```powershell
# Windows
./scripts/run_frontend.ps1
# macOS / Linux
./scripts/run_frontend.sh
```

The dashboard reads `VITE_SOLVER_API_URL` (see `frontend/.env.example`,
defaults to `http://localhost:8000`). Click **Run all 7 simulations** — each
scenario is solved by the live backend and its routes are drawn on the map. If
the backend is offline, the feed shows `LOCAL ENGINE` and the map falls back to
the client-side Dijkstra preview, so the demo never breaks.

### Quick API check
```powershell
$body = Get-Content samples/sample_optimize_request.json -Raw
Invoke-RestMethod -Uri http://localhost:8000/optimize -Method Post `
  -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6
```

---

## 5. Tests

```bash
python -m pytest -q        # 36 passed  (33 core/solver + 3 optimize endpoint)
cd frontend && npm run build   # type-checks + bundles the dashboard
```

**Verified end-to-end over HTTP**: server boots, `/health` ok, `/optimize`
returns 3 priority-aware routes (23 people routed, priority 45.5) in ~0.5 s,
respecting all closed roads.

---
marp: true
theme: default
paginate: true
title: Project Aegis Route
---

# Project Aegis Route
### Real-Time Agentic Optimization for Wildfire Search & Rescue

Unstructured intel → structured state → optimal routes — **live**.

Grounded in the **January 2025 Palisades Fire**.

`GraphRAG · Redis · LLM Agent · OR-Tools · React`

---

# The problem

In a wildfire, the map is **wrong within minutes**.

- Roads close, smoke shifts, new 911 calls land every second.
- A route computed 90s ago can drive a rescue team **into the fire**.
- Intel arrives as **unstructured chaos**: 911 transcripts, fire-dept radio,
  weather feeds, social posts.

**Re-solving from raw text on every update is too slow and too expensive.**

We need a system that turns chaos into an O(1) live state — and re-routes in real time.

---

# Grounded in real data (Jan 2025 Palisades Fire)

Not a toy graph — the demo is built on real public datasets:

| Source | What it gives us |
|---|---|
| **LAFD fire progression** | 11 timestamped perimeters, Jan 7–11 2025 |
| **OpenStreetMap (Overpass)** | the actual Palisades road network |
| **USGS 3DEP** | elevation raster for terrain-aware cost |
| **EPA AirNow** | PM2.5 smoke-risk field |

Bounding box `-118.72, 33.99, -118.46, 34.16`. Fire perimeters are **replayed
in time order** so the map evolves exactly as the real fire did.

---

# Architecture: two layers, decoupled

```
  911 · fire-dept · weather · social   (unstructured)
                  |
        extractor_agent  (LLM + rule-engine fallback)
                  |
  GraphRAG static graph  --->  REDIS live state  (O(1) edge weights, priorities)
   (roads/terrain, indexed once)        |
                            contract_builder -> Matrix Payload JSON
                                        |
     React dashboard  <--/optimize-->  FastAPI  ->  OR-Tools solver
        (SVG tactical map)         (/solve /optimize /ws/routes)
```

- **GraphRAG** = what rarely changes (topology, terrain) — pre-indexed once.
- **Redis** = what changes every second (live costs, priorities) — O(1).

---

# The agentic pipeline

Every piece of intel flows through one normalized path:

1. **`ingest.py`** — multi-source adapters (phone, API, social) → one schema.
2. **`extractor_agent.py`** — LLM turns *"bridge out on Route 4"* into a
   structured edge update. Deterministic **rule-engine fallback** if the LLM is down.
3. **`redis_store.py`** — writes a live multiplier. `final_cost = base × multiplier`.
4. **`contract_builder.py`** — assembles the **Matrix Payload** the solver consumes.
5. **`solver_bridge.py`** — runs the solver, writes the solution back,
   **publishes** on `aegis:updates` + `/ws/routes` for the dashboard.

> Telemetry (continuous, O(1)) is **decoupled** from solving (on-demand).

---

# Why Redis is the right call

- **O(1) live edge weights** — one `"Route 4 blocked"` = one `HSET`, not a re-parse.
- **`final_cost = base × multiplier`** — static topology stays put; only the
  thin live layer moves.
- **Pub/Sub** (`aegis:contract:update`, `aegis:routes:update`) streams updates
  straight to the dashboard — no polling.
- **Graceful by default** — runs on `fakeredis` out of the box, **auto-upgrades**
  to real Redis (incl. RediSearch) when available.

---

# Semantic cache: don't pay to think twice

Paraphrased intel (*"fire on 4"* ≈ *"Route 4 is burning"*) shouldn't trigger a
second LLM call. **`semantic_cache.py`** = RediSearch vector cache (NumPy fallback).

**Live harness — 12,000 ticks, re-solve every 25:**

| Metric | Result |
|---|---|
| Solver runs | **480** |
| Cache hit rate | **96.0%** |
| LLM tokens saved | **4.84 million** |
| Invariants | **all held, zero crashes** |

---

# The real solver (not a black box)

A full optimization subsystem (`solver/`, FastAPI) — **never the LLM routing**:

- **OR-Tools CVRP** — capacity-constrained, **priority-aware triage** (drops
  lowest-priority sites when the fleet can't serve everyone).
- **TSP-LKH + 2-opt** refinement for per-vehicle ordering.
- **Optional PyTorch ML warm-start** — degrades cleanly to nearest-neighbor.
- Served via **`/solve`, `/optimize`, `/health`, `/ws/routes`** (live WebSocket).

The `/optimize` endpoint solves on the **same 24-node grid the map renders**,
so routes come back as drawable `svg_path` + `ordered_nodes`.

---

# The dashboard (React + Vite + TS)

- Live **SVG tactical map**, incident feed, operations sidebar.
- Calls the real backend `/optimize`; **falls back to a local Dijkstra preview**
  if the API is offline — the demo never hard-fails.
- Per-vehicle routes, `SOLVER: LIVE / OFFLINE` badge, real metrics in the feed.
- Palisades-specific views: `PalisadesMap`, `DynamicMissionMap`, `NodeSelector`,
  `DemoGuide`.

---

# The killer demo: continue-or-retreat

**Fire Station 6** is the safe base. Rescue sites **N9 · N15 · N21** are inside the fire.

1. Sites ranked by **fire-distance priority + round-trip cost**; team takes the
   lowest-cost route, loads survivors, returns, marks the site safe.
2. A **concurrent ambulance** from **Hospital 14** runs its own queue
   (5 medical calls, capacity 3) — independent route, blue/purple styling.
3. The **LAFD perimeter keeps advancing**; fire-exposed edges gain rising
   risk + travel weight in Redis.
4. A mid-mission **flare-up injects a `LIVE N1000` split node** (yellow ring).
   The optimizer weighs distance-remaining vs retreat vs fire exposure vs
   alternative cost vs priority — and **re-routes or retreats, live**.

---

# One O(1) write, end to end

> A 911 caller says *"the fire jumped Sunset by the village."*
>
> → `extractor_agent` → **one Redis multiplier write** → `contract_builder`
> rebuilds the Matrix Payload → OR-Tools re-solves → the chevron on the React
> map **snaps around the new hazard** — in real time.

That single thread is the whole product.

---

# Engineering rigor

- **38 tests** green (unit + integration + realtime + traversal + `/optimize`).
- Fallbacks at **every** layer: LLM→rules, RediSearch→NumPy, real-Redis→fakeredis,
  Torch→nearest-neighbor, backend→local Dijkstra.
- Self-improving harness caught a real **O(n) cache bug** → vectorized to O(1)-amortized.
- Decoupled, replayable, and **demo-proof** offline.

---

# Tech stack

| Layer | Tech |
|---|---|
| Live state | **Redis** (+ RediSearch), pub/sub |
| Knowledge | **GraphRAG** static graph + local search |
| Agent | **LLM extractor** + rule-engine fallback + semantic cache |
| Optimizer | **OR-Tools CVRP**, TSP-LKH, 2-opt, PyTorch warm-start |
| Backend | **FastAPI** (`/optimize`, `/solve`, `/ws/routes`) |
| Frontend | **React + Vite + TypeScript**, SVG tactical map |
| Data | LAFD · OpenStreetMap · USGS 3DEP · EPA AirNow |

---

# Run it

```bash
# 1) Solver backend  ->  http://localhost:8000
./scripts/run_backend.ps1        # (.sh on macOS/Linux)

# 2) Dashboard       ->  http://localhost:5173
./scripts/run_frontend.ps1

# Headless agentic pipeline demo
pip install -r requirements.txt && python demo.py

# Tests
python -m pytest -q              # 38 passed
```

---

# Thank you

**Aegis Route** — chaos in, optimal rescue routes out, live.

Real fire data · O(1) live state · real optimizer · real dashboard.

`github.com/A-Sanil/CalHacks`

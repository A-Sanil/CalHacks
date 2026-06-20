# Project Aegis Route — Real-Time Agentic Optimization for Disaster Logistics

> Unstructured situational intel → a live, traversable graph in **Redis** → a JSON
> **Matrix Payload** contract → **your** OR-Tools solver → optimized multi-vehicle
> routes streamed to a dashboard. This repo is everything **upstream of the solver**:
> ingestion, the extractor agent, the Redis state graph, GraphRAG traversal, the
> contract builder, and the closed feedback loop — all tested under continuous load.

---

## 0. The problem (from the architecture doc)

Disaster logistics is a **dynamic, non-Euclidean Vehicle Routing Problem under extreme,
evolving constraints**. A wildfire makes the map *change second-by-second*: bridges burn,
roads close, new casualties appear. A static shortest-path is useless 30 seconds later.

Aegis Route splits the job into two brains, each doing what it is good at:

| Brain | Job | Why |
|---|---|---|
| **LLM / Extractor Agent** | turn messy human/sensor text into structured graph deltas | LLMs are great at language, terrible at math |
| **OR-Tools Solver** | compute the optimal capacitated route | solvers are exact and fast; never let the LLM "pick a route" |

**Redis is the shared nervous system** between them: it holds every weight, every update is
O(1), and it carries the contract and the solution via pub/sub.

---

## 1. Architecture at a glance

```
 911 / ambulance / fire dept ─┐
 weather (NOAA) ──────────────┤
 Caltrans / road closures ────┤  ┌──────────┐   ┌────────────────────┐    ┌──────────────────────┐
 fire perimeter (CalFire) ────┼─▶│ ingest.py│──▶│ extractor_agent.py │──▶ │        REDIS         │
 radio / social ──────────────┘  │ normalize│   │ semantic cache +   │    │ edge:i:j base*mult   │ O(1)
                                 │ to Signal│   │ rules / LLM        │    │ node:id pri/demand   │
                                 └──────────┘   └────────────────────┘    └──────────┬───────────┘
                                                                                     │ traverse
                                                          graph_traversal.py ◀────────┤ (GraphRAG k-hop)
                                                          localized sub-graph         │
                                                                                     ▼
                                                          contract_builder.py  build JSON Matrix Payload
                                                          store IN redis  +  PUBLISH aegis:contract:update
                                                                                     │
                                                          solver_bridge.py  ─▶ YOUR OR-Tools solver
                                                          store_solution() + PUBLISH aegis:routes:update ─▶ Mapbox
```

---

## 2. The Redis data model (the O(1) state graph)

Everything the system knows lives in plain Redis structures. **A weight change is one `HSET`.**

```text
node:{id}            HASH   lat lng type demand priority tw_start tw_end
edge:{i}:{j}         HASH   base_cost  multiplier  reason
aegis:nodes          SET    all node ids                (index, avoids KEYS scans)
aegis:edges          SET    "i:j" strings              (index)
aegis:aliases        HASH   "hwy 9 bridge" -> "3:5"    (entity -> EDGE resolver)
aegis:node_aliases   HASH   "high school" -> "5"       (entity -> NODE resolver)
aegis:contract:latest  STRING  the built JSON contract (lives IN redis)
aegis:routes:latest    STRING  the solver's solution   (written back to redis)
```

**The core equation:**  `final_cost(i,j) = base_cost × multiplier`

- `base_cost` = the **preset** weight (from your OSM import). Set once.
- `multiplier` = the **live custom** weight the agent updates. `1.0` = normal, `1000` = impassable, `1.5` = degraded (smoke/wind).

Example of the actual bytes in Redis for one edge before and after a fire:

```text
# preset (seeded)
HGETALL edge:3:5   ->   base_cost=5.0   multiplier=1     reason=none      final = 5.0
# after "fire jumped Hwy 9 bridge" (ONE O(1) write)
HSET edge:3:5 multiplier 1000 reason "fire_dept:active_fire_front"
HGETALL edge:3:5   ->   base_cost=5.0   multiplier=1000  reason=...        final = 5000.0
```

> **Why this matters:** telemetry can hammer Redis with O(1) updates *constantly*, while you
> only call the (expensive) solver *on demand*. Update frequency is decoupled from solve
> frequency — that's why re-routing feels instant and you never rebuild a full cost matrix.

---

## 3. The demo graph (data you can inspect)

`graph_seed.py` loads a 10-node test map. Real deployments swap this for an OSM import.

| id | type | demand | priority | time window |
|---|---|---|---|---|
| 0 | depot_air (V1 start) | 0 | 0 | – |
| 1 | depot_ground (V2 start) | 0 | 0 | – |
| 2 | hospital | 0 | 10.0 | [0,240] |
| 3 | junction | 0 | 0 | – |
| 4 | junction | 0 | 0 | – |
| 5 | evacuee | 3 | 9.5 | [0,45] |
| 6 | evacuee | 6 | 7.0 | [0,90] |
| 7 | evacuee | 2 | 8.0 | [0,60] |
| 8 | evacuee | 10 | 4.0 | [0,120] |
| 9 | fire_front | 0 | 0 | – |

Base edges (undirected, `base_cost`): `0-3:6, 0-4:7, 3-5:5, 3-2:4, 4-6:6, 4-8:9, 1-8:8,
1-7:5, 7-2:4, 5-2:3, 6-8:5, 3-4:8, 5-7:6, 6-9:3, 3-9:4`.

Entity aliases the agent uses to map *language → graph*:
`"hwy 9 bridge"→(3,5)`, `"route 4"→(4,8)`, `"coastal road"→(1,8)`, `"ridge pass"→(4,6)`,
`"high school"/"evac point"→node 5`, `"north shelter"→node 6`, …

---

## 4. End-to-end traversal — a worked example, step by step

**Incoming call (unstructured):**
```
Engine 12 reporting structure fire jumped Hwy 9 bridge, road is impassable, do not route units through there.
```

### Step 1 — Ingest (normalize any source to one `Signal`)
`PhoneCallAdapter` (or Twilio→Whisper in prod) emits:
```json
{ "source": "phone_call", "channel": "fire_dept",
  "text": "Engine 12 ... Hwy 9 bridge, road is impassable, do not route ...",
  "ts": "2026-06-20T20:14:03Z", "meta": {"transcribed": true} }
```

### Step 2 — Semantic cache check (skip the LLM if we've seen a paraphrase)
`semantic_cache.lookup(text)` embeds the message and compares (cosine) to prior ones.
- First time → **MISS** → run extraction.
- Later, "structure fire on Hwy 9, road closed" → cosine ≈ 0.9 ≥ 0.86 → **HIT**, reuse the
  same deltas, **0 tokens**. (`tokens_saved += 420`.)

### Step 3 — Extract (language → structured deltas)
`extractor_agent` resolves entities and classifies intent:
- `resolve_alias("hwy 9 bridge")` → edge `(3,5)`
- keyword `"impassable"` ∈ HAZARD → multiplier `1000`
```json
[ {"target":"edge","i":3,"j":5,"multiplier":1000.0,"reason":"fire_dept:active_fire_front"} ]
```
(If `OPENAI_API_KEY` is set, an LLM produces this JSON instead; otherwise the rule engine does.)

### Step 4 — Write to Redis (O(1))
```text
HSET edge:3:5 multiplier 1000 reason "fire_dept:active_fire_front"
HSET edge:5:3 multiplier 1000 reason "fire_dept:active_fire_front"   # symmetric
```
`final_cost(3,5)` is now `5.0 × 1000 = 5000.0`.

### Step 5 — GraphRAG traversal (situational awareness of the affected area)
Before solving, the agent retrieves the **localized sub-graph** around the hazard
(`graph_traversal.py`):
1. `affected_centers(store)` → nodes touched by active hazards → `[3, 5]`
2. **BFS k-hop expansion** from those seeds. With `hops=1` we visit `{3,5}` and their
   neighbors `{0,2,4,9,7}`.
3. Collect every edge whose endpoints are inside the visited set, with current state:
```json
{ "nodes": [0,2,3,4,5,7,9],
  "edges": [
    {"edge":[3,5],"base_cost":5.0,"multiplier":1000.0,"final_cost":5000.0,"reason":"fire_dept:active_fire_front"},
    {"edge":[3,2],"base_cost":4.0,"multiplier":1.0,"final_cost":4.0,"reason":"none"},
    {"edge":[3,4],"base_cost":8.0,"multiplier":1.0,"final_cost":8.0,"reason":"none"},
    {"edge":[5,2],"base_cost":3.0,"multiplier":1.0,"final_cost":3.0,"reason":"none"}
  ] }
```
This is the traversal step the PDF calls "retrieve the localized sub-graph of the affected
area … complete situational awareness of impassable non-Euclidean terrains." The solver can
now scope to this neighborhood instead of the whole map.

### Step 6 — Build the JSON Matrix Payload (the Agent→Solver contract) and store it IN Redis
`contract_builder.build_contract(store)` reads Redis and emits:
```json
{
  "timestamp": "2026-06-20T20:14:04Z",
  "disaster_state": "escalating_wildfire",
  "vehicles": [
    {"id":"V1","type":"air_evac","capacity":4,"start_node":0},
    {"id":"V2","type":"ground_heavy","capacity":12,"start_node":1}
  ],
  "target_nodes": [
    {"id":2,"priority":10.0,"demand":0,"time_window":[0,240]},
    {"id":5,"priority":9.5,"demand":3,"time_window":[0,45]},
    {"id":7,"priority":8.0,"demand":2,"time_window":[0,60]},
    {"id":6,"priority":7.0,"demand":6,"time_window":[0,90]},
    {"id":8,"priority":4.0,"demand":10,"time_window":[0,120]}
  ],
  "dynamic_edge_modifiers": [
    {"edge":[3,5],"multiplier":1000.0,"reason":"fire_dept:active_fire_front"}
  ]
}
```
It is saved to `aegis:contract:latest` and **`PUBLISH aegis:contract:update`** fires.

### Step 7 — Solve (YOUR solver) and write the solution back
`solver_bridge.run_solver(store, your_solver_fn)` hands the contract to your OR-Tools solver.
Your function returns, and we persist + publish:
```json
{ "vehicles":[
    {"id":"V1","route":[0,5,2],"load":3,"cost":8.0},
    {"id":"V2","route":[1,7,6],"load":8,"cost":15.0}],
  "total_cost": 23.0, "dropped":[8] }
```
Stored at `aegis:routes:latest`; **`PUBLISH aegis:routes:update`** drives the Mapbox dashboard.
Note V1 reaches node 5 via `0→5` style paths that **avoid edge 3-5** because its cost is now 5000.

### Step 8 — Loop forever
`sim_realtime.py` keeps doing 1→7 on a live stream, asserting invariants every tick.

---

## 5. How the contract maps to OR-Tools (so your solver plugs straight in)

| Contract field | OR-Tools concept |
|---|---|
| `vehicles[].capacity` | per-vehicle capacity dimension |
| `target_nodes[].demand` | node demand on the capacity dimension |
| `target_nodes[].priority` | drop penalty (disjunction) ∝ priority — high priority = expensive to skip |
| `target_nodes[].time_window` | time dimension window per node |
| `dynamic_edge_modifiers` × `base_cost` | the arc cost matrix (`final_cost`) |
| `multiplier = 1000` | effectively forbids the arc (impassable) |

Plug in: `run_solver(store, my_solver)` where `my_solver(contract, store) -> {vehicles, total_cost, dropped}`.

---

## 6. Token efficiency (the Redis semantic-cache story)

The extractor never re-pays for messages it has effectively seen before:
- `semantic_cache.py` embeds each message (OpenAI embeddings if a key is set, else a
  deterministic local hashing embedding) and does cosine KNN.
- Backend = real **RediSearch vector index** on Redis Stack; **NumPy-vectorized, size-capped**
  in-memory fallback offline.
- Verified: across 12,000 live ticks, **61.3% cache hit-rate, ~3.09M tokens saved**.

---

## 7. Running it

```bash
pip install -r requirements.txt
python demo.py            # full end-to-end story (fakeredis, no keys)
python -m pytest -q       # 12 tests: store / contract / pubsub / semcache / solver / traversal / realtime
python stress.py          # 12,000 live ticks x 15 seeds, invariants asserted EVERY tick
python sim_realtime.py    # never-ending live stream (Ctrl+C to stop)
```
- Real Redis: `set AEGIS_REDIS_URL=redis://localhost:6379` (Redis Stack enables the RediSearch cache).
- LLM extraction + embeddings: `set OPENAI_API_KEY=...` (else transparent rules + local embeddings).

---

## 8. Files

| file | role |
|---|---|
| `redis_store.py` | base+live weights, node intel, contract/solution storage, pub/sub — all O(1) |
| `graph_seed.py` | demo graph + entity aliases (swap for OSM import) |
| `ingest.py` | one adapter per source → normalized `Signal` (add a source = add an adapter) |
| `extractor_agent.py` | unstructured text → edge/node deltas → Redis, backed by semantic cache |
| `semantic_cache.py` | paraphrase-aware cache (RediSearch / NumPy fallback) |
| `graph_traversal.py` | GraphRAG localized sub-graph (BFS k-hop) — the traversal step |
| `contract_builder.py` | build JSON Matrix Payload from Redis, store in Redis, publish |
| `solver_bridge.py` | run YOUR solver, write solution back, publish to dashboard |
| `sim_realtime.py` | continuous live simulator + invariant checks |
| `stress.py` | heavy multi-seed stress harness |
| `demo.py` | end-to-end demo |
| `tests/` | pytest suite (unit + integration + long-run invariants) |

---

## 9. How our final agent should understand, build, and improve this

**Mental model:** *language in → graph deltas → Redis (truth) → contract → solver → solution → repeat.*
The agent only ever (a) maps text to entities/intents and (b) emits structured deltas. It must
**never** compute distances or pick routes — that is the solver's job.

**To extend (each is local and safe):**
- **New data source** → add one adapter in `ingest.py` that yields `Signal`. Nothing downstream changes.
- **New entity** → add a name to `EDGE_ALIASES` / `NODE_ALIASES` (later: GraphRAG auto-populates these from briefing docs).
- **New intent** (e.g. road *partially* blocked → multiplier 3) → add a keyword/branch in `extractor_agent._rule_extract`, or improve the LLM prompt.
- **Real solver** → `run_solver(store, my_solver)`.
- **Smarter traversal** → raise `hops`, or weight expansion by priority in `graph_traversal.py`.

**To keep improving safely:** every change is guarded by the test suite + the invariant harness.
`stress.py` proves correctness under thousands of live ticks. Add a test, run `pytest`, then
`stress.py` — if invariants hold, the change is safe to ship.

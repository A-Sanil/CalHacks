---
marp: true
theme: default
paginate: true
title: Project Aegis Route
---

# Project Aegis Route
### Real-Time Agentic Optimization for Disaster Logistics
Unstructured intel → live Redis graph → JSON contract → OR-Tools → optimized routes

---

## The problem
- Disaster routing = **dynamic, non-Euclidean VRP under evolving constraints**
- The map changes second-by-second: bridges burn, roads close, casualties appear
- A static shortest path is wrong 30 seconds later
- **Need:** ingest chaos in plain language → re-optimize **instantly**

---

## Two brains, one nervous system
| Brain | Job | Why |
|---|---|---|
| **LLM / Extractor** | text → structured graph deltas | great at language, bad at math |
| **OR-Tools Solver** | optimal capacitated routes | exact & fast; never let the LLM route |

**Redis = the nervous system**: holds every weight, O(1) updates, carries contract + solution via pub/sub.

---

## Architecture

```
sources ─▶ ingest ─▶ extractor (semantic cache + rules/LLM) ─▶ REDIS (base*mult, O(1))
                                                                  │ traverse (GraphRAG k-hop)
                                            contract_builder ◀─────┘
                                            store IN redis + PUBLISH contract:update
                                                   │
                                            solver_bridge ─▶ YOUR solver
                                            store_solution + PUBLISH routes:update ─▶ Mapbox
```

---

## Redis data model
```text
node:{id}      HASH  lat lng type demand priority tw_start tw_end
edge:{i}:{j}   HASH  base_cost  multiplier  reason
aegis:aliases  HASH  "hwy 9 bridge" -> "3:5"
aegis:contract:latest / aegis:routes:latest  STRING
```
**final_cost(i,j) = base_cost × multiplier**
- base_cost = preset (OSM) · multiplier = live (1=ok, 1.5=degraded, 1000=impassable)
- **Every update = one HSET = O(1)** → no matrix rebuild

---

## Data example — one edge, before & after
```text
# seeded
edge:3:5  base_cost=5.0  multiplier=1     reason=none      final = 5.0
# "fire jumped Hwy 9 bridge"  (ONE O(1) write)
HSET edge:3:5 multiplier 1000 reason "fire_dept:active_fire_front"
edge:3:5  base_cost=5.0  multiplier=1000  reason=...        final = 5000.0
```
Update frequency (telemetry, constant) is **decoupled** from solve frequency (on demand).

---

## Traversal — step by step (1/2)
**Input:** "Engine 12: structure fire jumped Hwy 9 bridge, road impassable."
1. **Ingest** → Signal{source:phone_call, channel:fire_dept, text:…}
2. **Semantic cache** → miss first time; paraphrase later = HIT, 0 tokens
3. **Extract** → resolve "hwy 9 bridge"→(3,5); "impassable"→×1000
   `{"target":"edge","i":3,"j":5,"multiplier":1000,"reason":"fire_dept:active_fire_front"}`
4. **Redis O(1)** → `HSET edge:3:5 multiplier 1000` (+ symmetric)

---

## Traversal — step by step (2/2)
5. **GraphRAG traversal** — BFS k-hop from hazard seeds {3,5}:
```json
{ "nodes":[0,2,3,4,5,7,9],
  "edges":[{"edge":[3,5],"final_cost":5000.0,"reason":"...fire..."},
           {"edge":[3,2],"final_cost":4.0},{"edge":[5,2],"final_cost":3.0}] }
```
6. **Build contract** (stored IN redis) + PUBLISH contract:update
7. **Solve** (your OR-Tools) → routes that avoid edge 3-5 + write back + PUBLISH routes:update
8. **Loop forever**

---

## The JSON Matrix Payload (Agent → Solver contract)
```json
{ "timestamp":"2026-06-20T20:14:04Z", "disaster_state":"escalating_wildfire",
  "vehicles":[{"id":"V1","type":"air_evac","capacity":4,"start_node":0},
              {"id":"V2","type":"ground_heavy","capacity":12,"start_node":1}],
  "target_nodes":[{"id":2,"priority":10.0,"demand":0,"time_window":[0,240]},
                  {"id":5,"priority":9.5,"demand":3,"time_window":[0,45]}],
  "dynamic_edge_modifiers":[{"edge":[3,5],"multiplier":1000,"reason":"active_fire_front"}] }
```

---

## Contract → OR-Tools mapping
| Contract field | OR-Tools |
|---|---|
| vehicles[].capacity | capacity dimension |
| target_nodes[].demand | node demand |
| target_nodes[].priority | drop penalty (disjunction) ∝ priority |
| target_nodes[].time_window | time dimension window |
| modifiers × base_cost | arc cost matrix |
| multiplier=1000 | forbids the arc |

---

## Token efficiency — Redis semantic cache
- Embed each message → cosine KNN (RediSearch on Redis Stack; NumPy fallback offline)
- Paraphrases reuse prior extractions → **0 tokens**
- **Verified:** 12,000 ticks → **61.3% hit-rate, ~3.09M tokens saved**

---

## Proven under continuous load
```
12,000 live ticks · 15 seeds · 60 ticks/s
ALL INVARIANTS HELD every single tick
480 solver runs · 3,089,100 tokens saved · 61.3% cache hit
13 tests pass (store/contract/pubsub/semcache/solver/traversal/realtime)
```
Invariants: final=base×mult, modifier consistency, demand≥0, priority∈[0,10],
contract round-trips, solver respects capacity & covers all targets.

---

## How we extend & improve (safely)
- **New source** → one adapter in `ingest.py` (Twilio→Whisper, NOAA, Caltrans, FIRMS…)
- **New entity** → add an alias (GraphRAG can auto-populate from briefing docs)
- **New intent** → keyword branch or better LLM prompt
- **Real solver** → `run_solver(store, my_solver)`
- **Every change guarded by tests + the invariant stress harness**

---

## The demo moment
> Inject "fire crossed Route 4" → one O(1) Redis write → contract rebuilt →
> solver re-routes → Mapbox chevron snaps around the hazard — in real time.

# Thank you
`pip install -r requirements.txt && python demo.py`

"""
sim_realtime.py  --  continuous real-time simulation + invariant checks.
Floods the system with randomized multi-source live data, rebuilds the contract,
runs the (mock) solver on a cadence, and asserts system invariants every tick.

run_simulation(ticks, seed, solve_every) -> stats   (raises AssertionError on violation)
__main__ runs a long continuous stream printing periodic health.
"""
from __future__ import annotations
import random, time, json
from redis_store import AegisStore
from graph_seed import seed_demo, EDGE_ALIASES, NODE_ALIASES
from extractor_agent import ExtractorAgent
from contract_builder import build_contract
from solver_bridge import run_solver
from ingest import Signal

EDGE_NAMES = list(EDGE_ALIASES.keys())
NODE_NAMES = list(NODE_ALIASES.keys())
CHANNELS = ["ambulance", "fire_dept", "NOAA", "Caltrans", "CalFire", "dispatch", "twitter"]

HAZARD_TPL = ["fire jumped {e}, road impassable", "structure fire on {e}, do not route",
              "{e} closed due to active fire front", "mudslide, {e} washed out"]
CLEAR_TPL = ["{e} reopened, all clear", "{e} now passable, fire contained"]
DEGRADE_TPL = ["smoke reducing visibility near {e}", "red flag winds pushing fire toward {e}"]
CASUALTY_TPL = ["{n} casualties at {nd}, need transport", "{n} people stranded at {nd}, medical needed"]


def random_signal(rng: random.Random) -> Signal:
    ch = rng.choice(CHANNELS)
    kind = rng.choices(["hazard", "clear", "degrade", "casualty"], weights=[5, 2, 3, 4])[0]
    if kind == "casualty":
        txt = rng.choice(CASUALTY_TPL).format(n=rng.randint(1, 9), nd=rng.choice(NODE_NAMES))
    else:
        tpl = {"hazard": HAZARD_TPL, "clear": CLEAR_TPL, "degrade": DEGRADE_TPL}[kind]
        txt = rng.choice(tpl).format(e=rng.choice(EDGE_NAMES))
    return Signal(source="sim", channel=ch, text=f"{ch}: {txt}")


def check_invariants(store: AegisStore, contract=None, solution=None) -> None:
    # 1. final_cost == base * multiplier, multiplier > 0
    for (i, j) in store.all_edges():
        e = store.get_edge(i, j)
        base, mult = float(e["base_cost"]), float(e["multiplier"])
        assert mult > 0, f"edge {i}-{j} multiplier must be > 0"
        fc = store.get_final_cost(i, j)
        assert abs(fc - base * mult) < 1e-6, f"final_cost mismatch on {i}-{j}"
    # 2. active_modifiers <-> edges with mult != 1
    mods = {tuple(sorted(m["edge"])) for m in store.active_modifiers()}
    for (i, j) in store.all_edges():
        m = float(store.get_edge(i, j)["multiplier"])
        if abs(m - 1.0) > 1e-9:
            assert tuple(sorted((i, j))) in mods, f"missing modifier {i}-{j}"
    # 3. node sanity
    for nid in store.all_node_ids():
        n = store.get_node(nid)
        assert float(n.get("demand", 0)) >= 0, f"node {nid} negative demand"
        assert 0 <= float(n.get("priority", 0)) <= 10, f"node {nid} priority out of range"
    # 4. contract round-trips through redis
    if contract is not None:
        rt = store.get_contract()
        assert rt is not None and rt["timestamp"] == contract["timestamp"]
        assert json.loads(json.dumps(contract)) == contract
    # 5. solution consistency
    if solution is not None:
        targets = {t["id"] for t in store.get_contract()["target_nodes"]}
        routed, caps = [], {v["id"]: v["capacity"] for v in store.get_contract()["vehicles"]}
        for v in solution["vehicles"]:
            assert v["load"] <= caps[v["id"]], f"vehicle {v['id']} over capacity"
            routed += [n for n in v["route"] if n in targets]
        served = set(routed) | set(solution["dropped"])
        assert set(routed).isdisjoint(set(solution["dropped"])), "node both routed and dropped"
        assert served == targets, f"served {served} != targets {targets}"


def run_simulation(ticks: int = 300, seed: int = 1, solve_every: int = 20, verbose: bool = False) -> dict:
    rng = random.Random(seed)
    store = AegisStore()
    seed_demo(store)
    agent = ExtractorAgent(store)
    solves, contract, solution = 0, None, None
    for t in range(1, ticks + 1):
        res = agent.process(random_signal(rng))
        if verbose and t % 50 == 0:
            print(f"tick {t}: {res['thought']}")
        check_invariants(store)
        if t % solve_every == 0:
            contract = build_contract(store)
            solution = run_solver(store)
            check_invariants(store, contract, solution)
            solves += 1
    return {"ticks": ticks, "solves": solves, "cache": agent.cache_stats(),
            "active_modifiers": len(store.active_modifiers()),
            "last_total_cost": solution["total_cost"] if solution else None,
            "last_dropped": solution["dropped"] if solution else None}


if __name__ == "__main__":
    print("=== continuous real-time simulation (Ctrl+C to stop) ===")
    rng = random.Random()
    store = AegisStore(); seed_demo(store)
    agent = ExtractorAgent(store)
    sub = store.subscribe(AegisStore.CH_ROUTES)
    tick = 0
    try:
        while True:
            tick += 1
            agent.process(random_signal(rng))
            check_invariants(store)
            if tick % 15 == 0:
                c = build_contract(store)
                s = run_solver(store)
                check_invariants(store, c, s)
                msg = sub.get_message(timeout=0.1)
                print(f"[tick {tick}] solved | total_cost={s['total_cost']} dropped={s['dropped']} "
                      f"| mods={len(store.active_modifiers())} | cache={agent.cache_stats()} "
                      f"| dashboard_event={'yes' if msg else 'no'}")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("stopped. final cache:", agent.cache_stats())

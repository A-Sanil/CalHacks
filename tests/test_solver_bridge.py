from redis_store import AegisStore
from graph_seed import seed_demo
from contract_builder import build_contract
from solver_bridge import run_solver

def test_solver_writes_back_and_respects_capacity():
    s = AegisStore(); seed_demo(s)
    build_contract(s)
    sol = run_solver(s)
    assert s.get_solution()["total_cost"] == sol["total_cost"]
    caps = {v["id"]: v["capacity"] for v in s.get_contract()["vehicles"]}
    for v in sol["vehicles"]:
        assert v["load"] <= caps[v["id"]]
    targets = {t["id"] for t in s.get_contract()["target_nodes"]}
    routed = [n for v in sol["vehicles"] for n in v["route"] if n in targets]
    assert set(routed) | set(sol["dropped"]) == targets

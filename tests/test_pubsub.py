from redis_store import AegisStore
from graph_seed import seed_demo
from contract_builder import build_contract
from solver_bridge import run_solver

def _drain(ps, tries=5):
    for _ in range(tries):
        m = ps.get_message(timeout=0.2)
        if m and m.get("type") == "message":
            return m
    return None

def test_contract_and_routes_publish():
    s = AegisStore(); seed_demo(s)
    ps = s.subscribe(AegisStore.CH_CONTRACT, AegisStore.CH_ROUTES)
    build_contract(s)
    assert _drain(ps) is not None        # contract update fired
    run_solver(s)
    assert _drain(ps) is not None        # routes update fired -> dashboard

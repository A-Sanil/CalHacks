import json
from redis_store import AegisStore
from graph_seed import seed_demo
from contract_builder import build_contract

def test_contract_schema_and_storage():
    s = AegisStore(); seed_demo(s)
    s.set_edge_multiplier(3, 5, 1000, "fire_dept:active_fire_front")
    c = build_contract(s)
    for key in ("timestamp", "disaster_state", "vehicles", "target_nodes", "dynamic_edge_modifiers"):
        assert key in c
    assert any(m["edge"] in ([3, 5], [5, 3]) for m in c["dynamic_edge_modifiers"])
    rt = s.get_contract()                       # contract lives IN redis
    assert rt["timestamp"] == c["timestamp"]
    assert json.loads(json.dumps(c)) == c

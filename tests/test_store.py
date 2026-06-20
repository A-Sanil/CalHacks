from redis_store import AegisStore
from graph_seed import seed_demo

def fresh():
    s = AegisStore(); seed_demo(s); return s

def test_o1_update_reflected():
    s = fresh()
    assert s.get_final_cost(3, 5) == 5.0
    s.set_edge_multiplier(3, 5, 1000, "fire")   # single O(1) write
    assert s.get_final_cost(3, 5) == 5000.0
    assert float(s.get_edge(5, 3)["multiplier"]) == 1000.0  # symmetric

def test_active_modifiers_dedupe():
    s = fresh()
    s.set_edge_multiplier(3, 5, 1000, "fire")
    mods = s.active_modifiers()
    pairs = [tuple(sorted(m["edge"])) for m in mods]
    assert (3, 5) in pairs and len(pairs) == len(set(pairs))

def test_node_intel():
    s = fresh()
    s.set_node_field(5, "priority", 10)
    assert s.incr_node_field(5, "demand", 6) == 9.0  # was 3

def test_clear_removes_modifier():
    s = fresh()
    s.set_edge_multiplier(3, 5, 1000, "fire")
    assert any(tuple(sorted(m["edge"])) == (3, 5) for m in s.active_modifiers())
    s.set_edge_multiplier(3, 5, 1.0, "cleared")
    assert all(tuple(sorted(m["edge"])) != (3, 5) for m in s.active_modifiers())

from redis_store import AegisStore
from graph_seed import seed_demo
from graph_traversal import affected_centers, localized_subgraph, neighbors

def test_traversal_retrieves_affected_subgraph():
    s = AegisStore(); seed_demo(s)
    s.set_edge_multiplier(3, 5, 1000, "fire_dept:active_fire_front")
    centers = affected_centers(s)
    assert set(centers) == {3, 5}                      # hazard seeds
    sub = localized_subgraph(s, centers, hops=1)
    assert 3 in sub["nodes"] and 5 in sub["nodes"]     # affected nodes present
    # the hazardous edge is in the sub-graph with its blown-up final cost
    hot = [e for e in sub["edges"] if sorted(e["edge"]) == [3, 5]][0]
    assert hot["multiplier"] == 1000.0 and hot["final_cost"] == 5000.0

def test_hop_expansion_grows():
    s = AegisStore(); seed_demo(s)
    one = localized_subgraph(s, [3], hops=1)["nodes"]
    two = localized_subgraph(s, [3], hops=2)["nodes"]
    assert set(one).issubset(set(two)) and len(two) >= len(one)

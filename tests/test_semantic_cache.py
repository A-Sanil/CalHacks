from redis_store import AegisStore
from graph_seed import seed_demo
from semantic_cache import SemanticCache

def test_paraphrase_hits_and_unrelated_misses():
    s = AegisStore(); seed_demo(s)
    c = SemanticCache(s, threshold=0.6)
    c.add("fire jumped hwy 9 bridge road impassable", [{"x": 1}])
    val, sim = c.lookup("structure fire on hwy 9 bridge, road impassable closed")
    assert val == [{"x": 1}] and sim >= 0.6     # paraphrase reused
    val2, _ = c.lookup("weather is sunny and calm at the beach today")
    assert val2 is None                          # unrelated -> miss
    assert c.stats()["tokens_saved"] > 0

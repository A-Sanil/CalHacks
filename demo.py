"""
demo.py  --  end-to-end Aegis Route ingestion demo (no API keys, no live redis needed).
Run:  pip install -r requirements.txt  &&  python demo.py
"""
import json
from redis_store import AegisStore
from graph_seed import seed_demo
from ingest import MultiSourceIngestor
from extractor_agent import ExtractorAgent
from contract_builder import build_contract


def hr(t): print("\n" + "=" * 68 + f"\n  {t}\n" + "=" * 68)


def main():
    store = AegisStore()
    hr("1. SEED PRESET GRAPH INTO REDIS")
    seed_demo(store)

    hr("2. BASELINE CONTRACT (built FROM redis, stored IN redis)")
    base = build_contract(store)
    print(json.dumps(base, indent=2))

    hr("3. INGEST EVERYTHING (phone calls, weather, caltrans, fire, social)")
    agent = ExtractorAgent(store)
    ing = MultiSourceIngestor()
    feed = list(ing.stream())
    # feed one duplicate to show the cache working
    feed.append(feed[1])
    for sig in feed:
        res = agent.process(sig)
        print("  " + res["thought"])

    hr("4. REBUILT CONTRACT AFTER LIVE UPDATES")
    updated = build_contract(store)
    print("dynamic_edge_modifiers:")
    print(json.dumps(updated["dynamic_edge_modifiers"], indent=2))
    print("\ntop target_nodes (by priority):")
    print(json.dumps(updated["target_nodes"][:4], indent=2))

    hr("5. PROOF: CONTRACT LIVES IN REDIS (GET aegis:contract:latest)")
    from_redis = store.get_contract()
    print("timestamp:", from_redis["timestamp"])
    print("modifiers stored in redis:", len(from_redis["dynamic_edge_modifiers"]))

    hr("6. O(1) SPOT CHECK + CACHE STATS")
    e = store.get_edge(3, 5)
    print(f"edge 3-5 -> base={e['base_cost']} x mult={e['multiplier']} "
          f"= final {store.get_final_cost(3,5)}  (reason: {e['reason']})")
    print("cache:", agent.cache_stats())
    print("\n>>> Hand 'aegis:contract:latest' to YOUR solver. Done.")


if __name__ == "__main__":
    main()

"""graph_seed.py -- preset demo graph loaded into Redis. Swap for your OSM import."""
from redis_store import AegisStore

NODES = [
    (0, 37.10, -122.10, "depot_air",    0, 0.0,  0,   0),
    (1, 37.02, -122.02, "depot_ground", 0, 0.0,  0,   0),
    (2, 37.07, -122.08, "hospital",     0, 10.0, 0, 240),
    (3, 37.09, -122.05, "junction",     0, 0.0,  0,   0),
    (4, 37.05, -122.09, "junction",     0, 0.0,  0,   0),
    (5, 37.08, -122.03, "evacuee",      3, 9.5,  0,  45),
    (6, 37.04, -122.06, "evacuee",      6, 7.0,  0,  90),
    (7, 37.06, -122.01, "evacuee",      2, 8.0,  0,  60),
    (8, 37.01, -122.07, "evacuee",     10, 4.0,  0, 120),
    (9, 37.03, -122.04, "fire_front",   0, 0.0,  0,   0),
]
EDGES = [
    (0,3,6.0),(0,4,7.0),(3,5,5.0),(3,2,4.0),(4,6,6.0),(4,8,9.0),(1,8,8.0),
    (1,7,5.0),(7,2,4.0),(5,2,3.0),(6,8,5.0),(3,4,8.0),(5,7,6.0),(6,9,3.0),(3,9,4.0),
]
EDGE_ALIASES = {
    "route 3": (3,5), "hwy 9": (3,5), "highway 9": (3,5), "hwy 9 bridge": (3,5),
    "route 4": (4,8), "coastal road": (1,8), "ridge pass": (4,6),
    "river crossing": (3,4), "canyon road": (6,8), "main st": (7,2),
}
NODE_ALIASES = {
    "high school": 5, "evac point": 5, "north shelter": 6, "shelter": 6,
    "ridge camp": 7, "south camp": 8, "general hospital": 2, "clinic": 2,
}

def seed_demo(store: AegisStore) -> None:
    for nid, lat, lng, typ, dem, pri, ts, te in NODES:
        store.set_node(nid, lat=lat, lng=lng, type=typ, demand=dem, priority=pri, tw_start=ts, tw_end=te)
    for i, j, c in EDGES:
        store.set_base_edge(i, j, c)
    for name, (i, j) in EDGE_ALIASES.items():
        store.set_alias(name, i, j)
    for name, nid in NODE_ALIASES.items():
        store.set_node_alias(name, nid)
    print(f"[seed] {len(NODES)} nodes, {len(EDGES)} edges, "
          f"{len(EDGE_ALIASES)} edge-aliases, {len(NODE_ALIASES)} node-aliases loaded")

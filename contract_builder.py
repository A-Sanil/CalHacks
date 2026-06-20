"""
contract_builder.py  --  assemble the JSON Matrix-Payload contract FROM Redis,
then store the contract back INSIDE Redis (aegis:contract:latest).
Schema matches Project Aegis Route.
"""
from __future__ import annotations
from datetime import datetime, timezone
from redis_store import AegisStore

DEFAULT_VEHICLES = [
    {"id": "V1", "type": "air_evac",     "capacity": 4,  "start_node": 0},
    {"id": "V2", "type": "ground_heavy", "capacity": 12, "start_node": 1},
]
TARGET_TYPES = {"evacuee", "hospital"}


def build_contract(store: AegisStore, vehicles=None,
                   disaster_state: str = "escalating_wildfire") -> dict:
    targets = []
    for nid in store.all_node_ids():
        n = store.get_node(nid)
        if n.get("type") in TARGET_TYPES:
            targets.append({
                "id": nid,
                "priority": float(n.get("priority", 0)),
                "demand": int(float(n.get("demand", 0))),
                "time_window": [int(float(n.get("tw_start", 0))), int(float(n.get("tw_end", 0)))],
            })
    targets.sort(key=lambda x: -x["priority"])

    contract = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disaster_state": disaster_state,
        "vehicles": vehicles or DEFAULT_VEHICLES,
        "target_nodes": targets,
        "dynamic_edge_modifiers": store.active_modifiers(),
    }
    store.store_contract(contract)   # <-- the contract lives IN redis
    return contract

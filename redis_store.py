"""
redis_store.py  --  Project Aegis Route : Redis state layer.
PRESET base weights + LIVE O(1) multipliers/node-intel + contract + solution + pub/sub.

Keys:
  node:{id} HASH | edge:{i}:{j} HASH | aegis:nodes SET | aegis:edges SET
  aegis:aliases HASH | aegis:node_aliases HASH
  aegis:contract:latest STRING   (built JSON contract lives IN redis)
  aegis:routes:latest   STRING   (solver output written back to redis)
Channels:
  aegis:contract:update  (fires when a new contract is ready for the solver)
  aegis:routes:update    (fires when the solver writes a new solution -> dashboard)
"""
from __future__ import annotations
import os, json
from typing import Optional, Callable


def _connect():
    url = os.environ.get("AEGIS_REDIS_URL")
    if url:
        try:
            import redis
            r = redis.from_url(url, decode_responses=True)
            r.ping()
            print(f"[redis] connected to {url}")
            return r
        except Exception as e:
            print(f"[redis] real Redis unavailable ({e}); using fakeredis")
    import fakeredis
    return fakeredis.FakeStrictRedis(decode_responses=True)


class AegisStore:
    CH_CONTRACT = "aegis:contract:update"
    CH_ROUTES = "aegis:routes:update"

    def __init__(self, client=None):
        self.r = client or _connect()

    # ---------------- NODES ----------------
    def set_node(self, node_id: int, **attrs) -> None:
        self.r.hset(f"node:{node_id}", mapping={k: str(v) for k, v in attrs.items()})
        self.r.sadd("aegis:nodes", node_id)

    def get_node(self, node_id: int) -> dict:
        return self.r.hgetall(f"node:{node_id}")

    def all_node_ids(self) -> list[int]:
        return sorted(int(x) for x in self.r.smembers("aegis:nodes"))

    def set_node_field(self, node_id: int, field: str, value) -> None:
        self.r.hset(f"node:{node_id}", field, str(value))

    def incr_node_field(self, node_id: int, field: str, delta: float) -> float:
        cur = float(self.get_node(node_id).get(field, 0) or 0)
        new = cur + delta
        self.r.hset(f"node:{node_id}", field, str(new))
        return new

    # ---------------- EDGES : preset base ----------------
    def set_base_edge(self, i: int, j: int, base_cost: float, symmetric: bool = True) -> None:
        self._write_edge(i, j, base_cost)
        if symmetric:
            self._write_edge(j, i, base_cost)

    def _write_edge(self, i: int, j: int, base_cost: float) -> None:
        self.r.hset(f"edge:{i}:{j}", mapping={"base_cost": str(base_cost), "multiplier": "1", "reason": "none"})
        self.r.sadd("aegis:edges", f"{i}:{j}")

    # ---------------- EDGES : live multiplier (O(1)) ----------------
    def set_edge_multiplier(self, i: int, j: int, multiplier: float, reason: str = "", symmetric: bool = True) -> None:
        self.r.hset(f"edge:{i}:{j}", mapping={"multiplier": str(multiplier), "reason": reason})
        if symmetric and self.r.exists(f"edge:{j}:{i}"):
            self.r.hset(f"edge:{j}:{i}", mapping={"multiplier": str(multiplier), "reason": reason})

    def get_edge(self, i: int, j: int) -> dict:
        return self.r.hgetall(f"edge:{i}:{j}")

    def get_final_cost(self, i: int, j: int) -> Optional[float]:
        e = self.get_edge(i, j)
        return None if not e else float(e["base_cost"]) * float(e.get("multiplier", 1))

    def all_edges(self) -> list[tuple[int, int]]:
        out = []
        for s in self.r.smembers("aegis:edges"):
            a, b = s.split(":")
            out.append((int(a), int(b)))
        return sorted(out)

    def active_modifiers(self) -> list[dict]:
        seen, mods = set(), []
        for (i, j) in self.all_edges():
            e = self.get_edge(i, j)
            m = float(e.get("multiplier", 1))
            if abs(m - 1.0) < 1e-9:
                continue
            k = frozenset((i, j))
            if k in seen:
                continue
            seen.add(k)
            mods.append({"edge": [i, j], "multiplier": m, "reason": e.get("reason", "")})
        return mods

    # ---------------- ALIASES ----------------
    def set_alias(self, name: str, i: int, j: int) -> None:
        self.r.hset("aegis:aliases", name.lower(), f"{i}:{j}")

    def resolve_alias(self, text: str) -> Optional[tuple[int, int]]:
        al = self.r.hgetall("aegis:aliases"); t = text.lower()
        for name in sorted(al, key=len, reverse=True):
            if name in t:
                a, b = al[name].split(":"); return int(a), int(b)
        return None

    def set_node_alias(self, name: str, node_id: int) -> None:
        self.r.hset("aegis:node_aliases", name.lower(), str(node_id))

    def resolve_node_alias(self, text: str) -> Optional[int]:
        al = self.r.hgetall("aegis:node_aliases"); t = text.lower()
        for name in sorted(al, key=len, reverse=True):
            if name in t:
                return int(al[name])
        return None

    # ---------------- CONTRACT (stored IN redis + PUBLISH) ----------------
    def store_contract(self, contract: dict) -> int:
        blob = json.dumps(contract)
        self.r.set("aegis:contract:latest", blob)
        self.r.lpush("aegis:contract:history", blob)
        self.r.ltrim("aegis:contract:history", 0, 49)
        return self.r.publish(self.CH_CONTRACT, blob)   # FEATURE 1: pub/sub

    def get_contract(self) -> Optional[dict]:
        blob = self.r.get("aegis:contract:latest")
        return json.loads(blob) if blob else None

    # ---------------- SOLUTION (solver output back into redis) ----------------
    def store_solution(self, solution: dict) -> int:
        blob = json.dumps(solution)
        self.r.set("aegis:routes:latest", blob)
        self.r.lpush("aegis:routes:history", blob)
        self.r.ltrim("aegis:routes:history", 0, 49)
        return self.r.publish(self.CH_ROUTES, blob)     # FEATURE 1: pub/sub -> dashboard

    def get_solution(self) -> Optional[dict]:
        blob = self.r.get("aegis:routes:latest")
        return json.loads(blob) if blob else None

    def subscribe(self, *channels):
        ps = self.r.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(*channels)
        return ps

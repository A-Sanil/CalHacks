"""
extractor_agent.py  --  UNSTRUCTURED -> STRUCTURED brain.
Signal (free text) -> structured edge/node updates -> Redis (O(1)).
Now backed by SemanticCache (FEATURE 2): paraphrases reuse prior extractions.
"""
from __future__ import annotations
import os, re, json
from redis_store import AegisStore
from semantic_cache import SemanticCache
from ingest import Signal

HAZARD = ["impassable", "closed", "washed out", "collapse", "destroyed", "blocked",
          "do not route", "burn zone", "active fire", "structure fire", "jumped", "mudslide", " out"]
DEGRADE = ["smoke", "visibility", "gusts", "wind", "haze", "red flag", "pushing fire"]
CLEAR = ["reopened", "cleared", "passable", "contained", "all clear"]
CASUALTY = ["casualt", "patients", "stranded", "injured", "victims", "people", "evacuees", "medical", "transport", " evac"]


class ExtractorAgent:
    def __init__(self, store: AegisStore):
        self.store = store
        self.cache = SemanticCache(store)
        self.use_llm = bool(os.environ.get("OPENAI_API_KEY"))

    def process(self, sig: Signal) -> dict:
        cached_val, sim = self.cache.lookup(sig.text)
        if cached_val is not None:
            updates, cached = cached_val, True
        else:
            updates = self._llm_extract(sig) if self.use_llm else self._rule_extract(sig)
            self.cache.add(sig.text, updates)
            cached = False
        self._apply(updates)
        return {"signal": sig, "updates": updates, "cached": cached,
                "similarity": round(sim, 3), "thought": self._explain(sig, updates, cached)}

    def _apply(self, updates: list[dict]) -> None:
        for u in updates:
            if u["target"] == "edge":
                self.store.set_edge_multiplier(u["i"], u["j"], u["multiplier"], u["reason"])
            elif u["target"] == "node":
                if "priority" in u:
                    self.store.set_node_field(u["node"], "priority", u["priority"])
                if u.get("demand_inc"):
                    self.store.incr_node_field(u["node"], "demand", u["demand_inc"])

    def _rule_extract(self, sig: Signal) -> list[dict]:
        t = " " + sig.text.lower() + " "
        updates: list[dict] = []
        num = re.search(r"(\d+)\s*(?:casualt|patient|people|victims|injured|evacuee)", t)
        n = int(num.group(1)) if num else None
        node_id = self.store.resolve_node_alias(t)
        if node_id is not None and any(k in t for k in CASUALTY):
            upd = {"target": "node", "node": node_id, "priority": 10.0, "reason": f"{sig.channel}_casualty_report"}
            if n:
                upd["demand_inc"] = n
            updates.append(upd)
        edge = self.store.resolve_alias(t)
        if edge is not None:
            i, j = edge
            if any(k in t for k in HAZARD):
                updates.append({"target": "edge", "i": i, "j": j, "multiplier": 1000.0, "reason": f"{sig.channel}:active_fire_front"})
            elif any(k in t for k in CLEAR):
                updates.append({"target": "edge", "i": i, "j": j, "multiplier": 1.0, "reason": "cleared"})
            elif any(k in t for k in DEGRADE):
                updates.append({"target": "edge", "i": i, "j": j, "multiplier": 1.5, "reason": f"{sig.channel}:degraded_visibility"})
        return updates

    def _llm_extract(self, sig: Signal) -> list[dict]:
        try:
            from openai import OpenAI
            client = OpenAI()
            sys = ('Extract routing impacts as a JSON list. Items: '
                   '{"target":"edge|node","entity":"<name>","multiplier":<float>,'
                   '"priority":<float>,"demand_inc":<int?>,"reason":"<short>"}. JSON only.')
            resp = client.chat.completions.create(model="gpt-4o-mini", temperature=0,
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": sig.text}])
            items = json.loads(resp.choices[0].message.content)
            out = []
            for it in items:
                if it.get("target") == "edge":
                    e = self.store.resolve_alias(it.get("entity", ""))
                    if e:
                        out.append({"target": "edge", "i": e[0], "j": e[1],
                                    "multiplier": float(it.get("multiplier", 1000)), "reason": it.get("reason", "llm")})
                else:
                    nid = self.store.resolve_node_alias(it.get("entity", ""))
                    if nid is not None:
                        u = {"target": "node", "node": nid, "priority": float(it.get("priority", 10)), "reason": it.get("reason", "llm")}
                        if it.get("demand_inc"):
                            u["demand_inc"] = int(it["demand_inc"])
                        out.append(u)
            return out
        except Exception as e:
            print(f"[agent] LLM failed ({e}); using rules")
            return self._rule_extract(sig)

    def _explain(self, sig, updates, cached) -> str:
        tag = "CACHE HIT" if cached else "extracted"
        if not updates:
            return f"[{sig.source}/{sig.channel}] ({tag}) no routing impact"
        parts = []
        for u in updates:
            if u["target"] == "edge":
                parts.append(f"edge {u['i']}-{u['j']} x{u['multiplier']} ({u['reason']})")
            else:
                d = f" demand+{u['demand_inc']}" if u.get('demand_inc') else ""
                parts.append(f"node {u['node']} priority={u.get('priority')}{d} ({u['reason']})")
        return f"[{sig.source}/{sig.channel}] ({tag}) -> " + "; ".join(parts)

    def cache_stats(self) -> dict:
        return self.cache.stats()

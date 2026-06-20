"""
semantic_cache.py  --  FEATURE 2: semantic cache for the extractor (paraphrase-aware).
Backends: 'redisearch' (real Redis Stack vector index) | 'memory' (offline fallback).
Memory backend is NumPy-vectorized + size-capped (FIFO) so it stays fast at scale.
Embeddings: OpenAI if OPENAI_API_KEY set, else deterministic local hashing embedding.
"""
from __future__ import annotations
import os, re, math, hashlib, json
from typing import Optional

try:
    import numpy as _np
except Exception:
    _np = None

_TOKEN = re.compile(r"[a-z0-9]+")


def _local_embed(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    for tok in _TOKEN.findall(text.lower()):
        vec[int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class SemanticCache:
    def __init__(self, store, threshold: float = 0.86, dim: int = 256, max_entries: int = 5000):
        self.store = store
        self.threshold = threshold
        self.dim = dim
        self.max_entries = max_entries
        self.hits = self.misses = self.tokens_saved = 0
        self._vals: list = []
        self._mat = None          # numpy [N,dim] if numpy present
        self._pyvecs: list = []   # pure-python fallback vectors
        self.backend = self._init_backend()

    # ---- embeddings ----
    def embed(self, text: str) -> list[float]:
        if os.environ.get("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                v = OpenAI().embeddings.create(model="text-embedding-3-small", input=text).data[0].embedding
                n = math.sqrt(sum(x * x for x in v)) or 1.0
                return [x / n for x in v]
            except Exception:
                pass
        return _local_embed(text, self.dim)

    def _init_backend(self) -> str:
        try:
            from redis.commands.search.field import VectorField, TextField
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType
            d = len(self.embed("probe"))
            try:
                self.store.r.ft("aegis:semcache").info()
            except Exception:
                schema = (VectorField("vec", "FLAT", {"TYPE": "FLOAT32", "DIM": d, "DISTANCE_METRIC": "COSINE"}),
                          TextField("value"))
                self.store.r.ft("aegis:semcache").create_index(
                    schema, definition=IndexDefinition(prefix=["semcache:"], index_type=IndexType.HASH))
            return "redisearch"
        except Exception:
            return "memory"

    # ---- API ----
    def lookup(self, text: str):
        vec = self.embed(text)
        best_val, best_sim = None, -1.0
        if self.backend == "redisearch":
            hit = self._redisearch_knn(vec)
            if hit is not None:
                best_val, best_sim = hit
        elif _np is not None and self._mat is not None:
            sims = self._mat @ _np.asarray(vec)        # vectorized cosine (unit vectors)
            k = int(sims.argmax())
            best_sim, best_val = float(sims[k]), self._vals[k]
        else:
            for v, val in zip(self._pyvecs, self._vals):
                s = sum(x * y for x, y in zip(vec, v))
                if s > best_sim:
                    best_sim, best_val = s, val
        if best_val is not None and best_sim >= self.threshold:
            self.hits += 1
            self.tokens_saved += 420
            return best_val, best_sim
        self.misses += 1
        return None, best_sim

    def add(self, text: str, value) -> None:
        vec = self.embed(text)
        if self.backend == "redisearch":
            import struct
            key = "semcache:" + hashlib.md5(text.encode()).hexdigest()
            self.store.r.hset(key, mapping={"vec": struct.pack(f"{len(vec)}f", *vec), "value": json.dumps(value)})
            return
        self._vals.append(value)
        if _np is not None:
            row = _np.asarray(vec, dtype=_np.float32)[None, :]
            self._mat = row if self._mat is None else _np.vstack([self._mat, row])
        else:
            self._pyvecs.append(vec)
        if len(self._vals) > self.max_entries:        # FIFO eviction -> bounded memory + speed
            self._vals.pop(0)
            if _np is not None:
                self._mat = self._mat[1:]
            else:
                self._pyvecs.pop(0)

    def _redisearch_knn(self, vec):
        try:
            import struct
            from redis.commands.search.query import Query
            q = Query("*=>[KNN 1 @vec $bv AS score]").sort_by("score").dialect(2).return_fields("value", "score")
            res = self.store.r.ft("aegis:semcache").search(q, {"bv": struct.pack(f"{len(vec)}f", *vec)})
            if res.docs:
                d = res.docs[0]
                return json.loads(d.value), 1.0 - float(d.score)
        except Exception:
            return None
        return None

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"backend": self.backend, "entries": len(self._vals), "hits": self.hits, "misses": self.misses,
                "hit_rate_pct": round(self.hits / total * 100, 1) if total else 0.0,
                "tokens_saved": self.tokens_saved}

from __future__ import annotations

import hashlib
import json
from functools import lru_cache

import numpy as np

from solver.config import settings
from solver.core.schema import DynamicEdgeModifier, ProblemPayload
from solver.redis_client import MatrixStore


def _modifiers_fingerprint(modifiers: list[DynamicEdgeModifier]) -> str:
    payload = [(m.edge, m.multiplier, m.reason) for m in modifiers]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def apply_edge_modifiers(
    baseline: np.ndarray,
    modifiers: list[DynamicEdgeModifier],
    *,
    blocked_cost: float | None = None,
) -> np.ndarray:
    """Return a copy of baseline with dynamic multipliers applied (symmetric)."""
    blocked = blocked_cost if blocked_cost is not None else settings.blocked_cost
    matrix = baseline.copy()
    n = matrix.shape[0]

    for mod in modifiers:
        i, j = mod.edge
        if i < 0 or j < 0 or i >= n or j >= n:
            continue
        if mod.multiplier >= 500:
            cost = blocked
        else:
            cost = baseline[i, j] * mod.multiplier
        matrix[i, j] = cost
        matrix[j, i] = cost

    return matrix


class CostMatrixBuilder:
    """Builds modified cost matrices with LRU caching for fast re-solves."""

    def __init__(self, store: MatrixStore | None = None) -> None:
        self._store = store
        self._baseline: np.ndarray | None = None
        self._baseline_key: str | None = None

    def load_baseline(self, payload: ProblemPayload) -> np.ndarray:
        if payload.baseline_matrix is not None:
            matrix = np.asarray(payload.baseline_matrix, dtype=np.float64)
            self._baseline = matrix
            self._baseline_key = "inline"
            return matrix

        if self._store is None:
            raise ValueError("baseline_matrix required when Redis store is not configured")

        matrix = self._store.load_matrix()
        self._baseline = matrix
        self._baseline_key = settings.matrix_key
        return matrix

    @lru_cache(maxsize=32)
    def _cached_modified(self, baseline_key: str, fingerprint: str, modifiers_json: str) -> np.ndarray:
        del fingerprint  # part of cache key via modifiers_json + baseline_key
        baseline = self._baseline
        if baseline is None:
            raise RuntimeError("baseline matrix not loaded")
        modifiers = [
            DynamicEdgeModifier(**item) for item in json.loads(modifiers_json)
        ]
        return apply_edge_modifiers(baseline, modifiers)

    def build(self, payload: ProblemPayload) -> np.ndarray:
        baseline = self.load_baseline(payload)
        if not payload.dynamic_edge_modifiers:
            return baseline.copy()

        modifiers_json = json.dumps(
            [m.model_dump() for m in payload.dynamic_edge_modifiers],
            sort_keys=True,
        )
        fingerprint = _modifiers_fingerprint(payload.dynamic_edge_modifiers)
        return self._cached_modified(self._baseline_key or "inline", fingerprint, modifiers_json)

    def invalidate_cache(self) -> None:
        self._cached_modified.cache_clear()

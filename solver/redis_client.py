from __future__ import annotations

import json
from typing import Any

import numpy as np
import redis

from solver.config import settings


class MatrixStore:
    """Loads baseline distance matrix and node coordinates from Redis."""

    def __init__(self, client: redis.Redis | Any) -> None:
        self._client = client

    def load_matrix(self) -> np.ndarray:
        raw = self._client.get(settings.matrix_key)
        if raw is None:
            raise KeyError(f"Redis key '{settings.matrix_key}' not found")
        data = json.loads(raw)
        matrix = np.asarray(data, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError("distance matrix must be square")
        return matrix

    def load_coords(self) -> np.ndarray | None:
        raw = self._client.get(settings.node_coords_key)
        if raw is None:
            return None
        data = json.loads(raw)
        return np.asarray(data, dtype=np.float64)

    def save_matrix(self, matrix: np.ndarray) -> None:
        payload = matrix.tolist()
        self._client.set(settings.matrix_key, json.dumps(payload))

    def save_coords(self, coords: np.ndarray) -> None:
        self._client.set(settings.node_coords_key, json.dumps(coords.tolist()))


def create_redis_client(url: str | None = None) -> redis.Redis:
    return redis.from_url(url or settings.redis_url, decode_responses=True)

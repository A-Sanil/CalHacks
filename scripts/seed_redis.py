from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from solver.redis_client import MatrixStore, create_redis_client


def euclidean_matrix(coords: np.ndarray) -> np.ndarray:
    diff = coords[:, None, :] - coords[None, :, :]
    return np.sqrt((diff ** 2).sum(axis=-1))


def seed_demo_graph(n_nodes: int = 20, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    coords = rng.random((n_nodes, 2)) * 100
    matrix = euclidean_matrix(coords)
    return matrix, coords


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Redis with baseline distance matrix")
    parser.add_argument("--nodes", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--redis-url", default=None)
    parser.add_argument("--dump", type=Path, default=None, help="Also write JSON files locally")
    args = parser.parse_args()

    matrix, coords = seed_demo_graph(args.nodes, args.seed)
    client = create_redis_client(args.redis_url)
    store = MatrixStore(client)
    store.save_matrix(matrix)
    store.save_coords(coords)
    print(f"Seeded {args.nodes}x{args.nodes} matrix + coords to Redis")

    if args.dump:
        args.dump.mkdir(parents=True, exist_ok=True)
        (args.dump / "distance_matrix.json").write_text(json.dumps(matrix.tolist()))
        (args.dump / "node_coords.json").write_text(json.dumps(coords.tolist()))
        print(f"Wrote local dumps to {args.dump}")


if __name__ == "__main__":
    main()

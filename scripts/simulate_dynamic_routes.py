from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import websockets


def build_demo_matrix(n: int = 12, seed: int = 0) -> tuple[list[list[float]], list[tuple[float, float]]]:
    rng = np.random.default_rng(seed)
    coords = rng.random((n, 2)) * 100
    diff = coords[:, None, :] - coords[None, :, :]
    matrix = np.sqrt((diff ** 2).sum(axis=-1))
    return matrix.tolist(), [(float(x), float(y)) for x, y in coords]


def base_payload(matrix: list[list[float]], coords: list[tuple[float, float]]) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disaster_state": "stable",
        "vehicles": [
            {"id": "V1", "type": "ground_heavy", "capacity": 20, "start_node": 0},
            {"id": "V2", "type": "air_evac", "capacity": 8, "start_node": 1},
        ],
        "target_nodes": [
            {"id": 5, "priority": 9.5, "demand": 3, "time_window": [0, 200]},
            {"id": 8, "priority": 4.0, "demand": 2, "time_window": [0, 200]},
            {"id": 11, "priority": 7.0, "demand": 4, "time_window": [0, 200]},
        ],
        "dynamic_edge_modifiers": [],
        "baseline_matrix": matrix,
        "node_coords": coords,
    }


async def run_ws_demo(solver_url: str, interval: float) -> None:
    matrix, coords = build_demo_matrix()
    payload = base_payload(matrix, coords)
    ws_url = solver_url.replace("http", "ws") + "/ws/routes"

    async with websockets.connect(ws_url) as ws:
        print(f"Connected to {ws_url}")
        for step in range(5):
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
            payload["disaster_state"] = ["stable", "escalating_wildfire", "critical"][min(step, 2)]
            if step >= 2:
                payload["dynamic_edge_modifiers"] = [
                    {"edge": [3, 5], "multiplier": 1000, "reason": "active_fire_front"},
                    {"edge": [1, 8], "multiplier": 1.5, "reason": "smoke_visibility_low"},
                ]
            else:
                payload["dynamic_edge_modifiers"] = []

            await ws.send(json.dumps(payload))
            response = json.loads(await ws.recv())
            print(
                f"[{step}] {response['disaster_state']} "
                f"solve={response['solve_time_ms']:.1f}ms "
                f"vehicles={len(response['vehicles'])}"
            )
            for v in response["vehicles"]:
                print(f"  {v['id']}: {v['path']}")
            await asyncio.sleep(interval)


def run_http_demo(solver_url: str, interval: float) -> None:
    matrix, coords = build_demo_matrix()
    payload = base_payload(matrix, coords)

    with httpx.Client(base_url=solver_url, timeout=30.0) as client:
        for step in range(5):
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
            payload["disaster_state"] = "escalating_wildfire" if step >= 2 else "stable"
            payload["dynamic_edge_modifiers"] = (
                [{"edge": [3, 5], "multiplier": 1000, "reason": "active_fire_front"}]
                if step >= 2
                else []
            )
            t0 = time.perf_counter()
            resp = client.post("/solve", json=payload)
            resp.raise_for_status()
            data = resp.json()
            print(f"[{step}] solved in {(time.perf_counter()-t0)*1000:.1f}ms (server: {data['solve_time_ms']:.1f}ms)")
            for route in data["routes"]:
                print(f"  {route['vehicle_id']}: {route['path']}")
            time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate dynamic re-routing for dashboard dev")
    parser.add_argument("--solver-url", default="http://localhost:8000")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--mode", choices=["http", "ws"], default="ws")
    args = parser.parse_args()

    if args.mode == "ws":
        asyncio.run(run_ws_demo(args.solver_url, args.interval))
    else:
        run_http_demo(args.solver_url, args.interval)


if __name__ == "__main__":
    main()

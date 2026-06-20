from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from solver.config import settings
from solver.core.matrix import CostMatrixBuilder
from solver.core.schema import ProblemPayload, SolveResponse
from solver.core.solver import SolverEngine
from solver.redis_client import create_redis_client


class ConnectionManager:
    """Broadcasts route updates to dashboard clients."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        async with self._lock:
            connections = list(self._connections)
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


def _incoming_event(payload: ProblemPayload) -> dict[str, Any]:
    return {
        "type": "update_received",
        "timestamp": payload.timestamp.isoformat(),
        "disaster_state": payload.disaster_state,
        "edge_modifiers_applied": [
            {"edge": list(m.edge), "multiplier": m.multiplier, "reason": m.reason}
            for m in payload.dynamic_edge_modifiers
        ],
    }


async def _solve_and_broadcast(payload: ProblemPayload) -> SolveResponse:
    await manager.broadcast(_incoming_event(payload))
    engine = get_engine()
    result = engine.solve(payload)
    await manager.broadcast(result.to_dashboard_event())
    return result


VIZ_DIR = Path(__file__).resolve().parents[2] / "viz"

manager = ConnectionManager()
_engine: SolverEngine | None = None


def get_engine() -> SolverEngine:
    global _engine
    if _engine is None:
        try:
            client = create_redis_client()
            client.ping()
            _engine = SolverEngine.from_redis(client)
        except Exception:
            _engine = SolverEngine(CostMatrixBuilder())
    return _engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-load solver (and ML model) at startup
    get_engine()
    yield
    if _engine is not None:
        _engine._matrix_builder.invalidate_cache()


app = FastAPI(
    title="AOE Solver",
    description="Real-time CVRP/TSP solver for Agentic Optimization Engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if VIZ_DIR.is_dir():
    app.mount("/viz", StaticFiles(directory=str(VIZ_DIR), html=True), name="viz")


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/viz/")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "aoe-solver"}


@app.post("/solve", response_model=SolveResponse)
async def solve(payload: ProblemPayload) -> SolveResponse:
    """
    Step C entrypoint: accept JSON matrix payload, return optimal routes.
    Also broadcasts to WebSocket subscribers for live dashboard updates.
    """
    try:
        result = await _solve_and_broadcast(payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Baseline matrix unavailable: {exc}. Seed Redis or pass baseline_matrix.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result


@app.websocket("/ws/routes")
async def websocket_routes(websocket: WebSocket) -> None:
    """
    Dashboard integration socket.
    Clients receive `route_update` events after each /solve call.
    Clients may also send ProblemPayload JSON to trigger inline re-solve.
    """
    await manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            payload = ProblemPayload.model_validate(data)
            await _solve_and_broadcast(payload)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as exc:
        await manager.disconnect(websocket)
        raise exc


def main() -> None:
    import uvicorn

    uvicorn.run(
        "solver.api.app:app",
        host=settings.solver_host,
        port=settings.solver_port,
        reload=False,
    )


if __name__ == "__main__":
    main()

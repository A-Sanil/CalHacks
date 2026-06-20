"""
optimize.py  --  /optimize endpoint: the dashboard's live solve path.

Accepts the frontend OptimizationRequest (a subset of ProblemPayload, sans matrix),
builds a LIVE cost matrix on the 24-node tactical grid (frontend_graph) with the
request's dynamic_edge_modifiers applied, runs the REAL SolverEngine (OR-Tools
CVRP), and returns OptimizedRoute[] with ordered_nodes + svg_path drawn on that
same grid so the map renders the true road paths the solver chose.

Mirrors solver/adapters/aegis_contract.py: matrix supplied inline via
baseline_matrix, dynamic_edge_modifiers emptied (weights already baked in).
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from solver.api import frontend_graph as fg
from solver.core.schema import ProblemPayload
from solver.core.solver import SolverEngine

router = APIRouter()


class OptimizedRoute(BaseModel):
    vehicle_id: str
    ordered_nodes: list[int]
    svg_path: str
    eta_minutes: float
    priority_served: float


class OptimizationMetrics(BaseModel):
    people_routed: int
    total_priority_served: float


class OptimizationResult(BaseModel):
    generated_at: str
    solve_time_ms: float
    routes: list[OptimizedRoute]
    metrics: OptimizationMetrics


_engine: SolverEngine | None = None


def get_engine() -> SolverEngine:
    global _engine
    if _engine is None:
        _engine = SolverEngine.from_redis(None)
    return _engine


@router.post("/optimize", response_model=OptimizationResult)
async def optimize(request: ProblemPayload) -> OptimizationResult:
    """Solve on the live tactical grid and return map-ready routes."""
    # 1) live adjacency with edge modifiers applied; all-pairs for matrix + paths
    adj = fg.live_adjacency(request.dynamic_edge_modifiers)
    matrix = fg.cost_matrix(adj)
    _dist, prevs = fg.all_pairs(adj)
    coords = fg.node_coords()

    # 2) rebuild payload with the live matrix baked in (modifiers already applied)
    payload = ProblemPayload(
        timestamp=request.timestamp,
        disaster_state=request.disaster_state,
        vehicles=request.vehicles,
        target_nodes=request.target_nodes,
        dynamic_edge_modifiers=[],
        visited_nodes=request.visited_nodes,
        baseline_matrix=matrix,
        node_coords=[tuple(c) for c in coords],
    )

    # 3) run the REAL solver
    response = get_engine().solve(payload)

    # 4) map RouteResult -> OptimizedRoute, expanding waypoints into full road paths
    routes: list[OptimizedRoute] = []
    people = 0
    prio = 0.0
    for r in response.routes:
        ordered = fg.expand_waypoints(list(r.path), prevs)
        routes.append(
            OptimizedRoute(
                vehicle_id=r.vehicle_id,
                ordered_nodes=ordered,
                svg_path=fg.svg_path(ordered),
                eta_minutes=round(float(r.cost), 1),
                priority_served=round(float(r.priority_collected), 2),
            )
        )
        people += int(r.demands_served)
        prio += float(r.priority_collected)

    return OptimizationResult(
        generated_at=response.timestamp.isoformat(),
        solve_time_ms=round(float(response.solve_time_ms), 2),
        routes=routes,
        metrics=OptimizationMetrics(
            people_routed=people,
            total_priority_served=round(prio, 2),
        ),
    )

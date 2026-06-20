from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np

from solver.algorithms.cvrp import solve_cvrp_ortools
from solver.algorithms.ml_warmstart import WarmStartModel, ensure_warmstart_model
from solver.algorithms.nearest_neighbor import nearest_neighbor_tour, tour_cost
from solver.algorithms.path_utils import solve_sparse_tsp
from solver.config import settings
from solver.core.matrix import CostMatrixBuilder
from solver.core.schema import ProblemPayload, RouteResult, SolveResponse
from solver.redis_client import MatrixStore


class SolverEngine:
    """
    Orchestrates matrix build + algorithm selection + incremental re-solve.
    """

    def __init__(
        self,
        matrix_builder: CostMatrixBuilder | None = None,
        *,
        use_ml: bool | None = None,
    ) -> None:
        self._matrix_builder = matrix_builder or CostMatrixBuilder()
        self._previous_routes: dict[str, list[int]] = {}
        self._warmstart: WarmStartModel | None = None
        self._use_ml = use_ml if use_ml is not None else settings.use_ml_warmstart

    def _get_warmstart(self) -> WarmStartModel | None:
        if not self._use_ml:
            return None
        if self._warmstart is None:
            try:
                self._warmstart = ensure_warmstart_model(
                    epochs=25,
                    n_instances=80,
                    n_nodes=16,
                )
            except Exception:
                self._warmstart = None
        return self._warmstart

    def _apply_visit_penalties(
        self,
        matrix: np.ndarray,
        payload: ProblemPayload,
    ) -> np.ndarray:
        """Penalize re-entering already visited nodes (except start + remaining targets)."""
        visited = set(payload.visited_nodes or [])
        if not visited:
            return matrix

        exempt = {t.id for t in payload.target_nodes} | {v.start_node for v in payload.vehicles}
        penalized = matrix.copy()
        visit_penalty = min(settings.blocked_cost / 5, 1e7)

        for node in visited:
            if node in exempt:
                continue
            for i in range(penalized.shape[0]):
                if i == node:
                    continue
                current = penalized[i, node]
                if current >= settings.blocked_cost / 2:
                    continue
                penalized[i, node] = min(current * 25, visit_penalty)
                penalized[node, i] = penalized[i, node]

        return penalized

    def solve(self, payload: ProblemPayload) -> SolveResponse:
        t0 = time.perf_counter()
        matrix = self._matrix_builder.build(payload)
        matrix = self._apply_visit_penalties(matrix, payload)
        coords = self._load_coords(payload, matrix.shape[0])

        if len(payload.vehicles) == 1 and not self._needs_cvrp(payload):
            response = self._solve_single_vehicle_tsp(payload, matrix, coords)
        else:
            response = self._solve_multi_vehicle(payload, matrix)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        response.solve_time_ms = elapsed_ms
        response.timestamp = payload.timestamp
        response.disaster_state = payload.disaster_state
        response.edge_modifiers_applied = payload.dynamic_edge_modifiers
        coords = self._load_coords(payload, matrix.shape[0])
        response.metadata["node_coords"] = coords.tolist()
        response.metadata["target_nodes"] = [t.model_dump() for t in payload.target_nodes]

        for route in response.routes:
            self._previous_routes[route.vehicle_id] = route.path

        return response

    def _needs_cvrp(self, payload: ProblemPayload) -> bool:
        if len(payload.vehicles) > 1:
            return True
        vehicle = payload.vehicles[0]
        total_demand = sum(t.demand for t in payload.target_nodes)
        if total_demand > vehicle.capacity:
            return True
        for target in payload.target_nodes:
            start, end = target.time_window
            if end < 9999:
                return True
        return False

    def _load_coords(self, payload: ProblemPayload, n: int) -> np.ndarray:
        if payload.node_coords is not None:
            return np.asarray(payload.node_coords, dtype=np.float64)
        if self._matrix_builder._store is not None:
            coords = self._matrix_builder._store.load_coords()
            if coords is not None:
                return coords
        # Fallback: derive pseudo-coords from matrix (MDS-like stub using row index)
        return np.column_stack([np.arange(n), np.zeros(n)])

    def _solve_single_vehicle_tsp(
        self,
        payload: ProblemPayload,
        matrix: np.ndarray,
        coords: np.ndarray,
    ) -> SolveResponse:
        vehicle = payload.vehicles[0]
        targets = [t.id for t in payload.target_nodes]

        path, cost, solver_used = solve_sparse_tsp(
            matrix, vehicle.start_node, targets
        )

        priority_collected = sum(
            t.priority for t in payload.target_nodes if t.id in path
        )
        demands_served = sum(
            t.demand for t in payload.target_nodes if t.id in path
        )

        return SolveResponse(
            timestamp=datetime.now(timezone.utc),
            disaster_state=payload.disaster_state,
            solve_time_ms=0.0,
            solver_used=solver_used,
            total_cost=cost,
            total_priority=priority_collected,
            routes=[
                RouteResult(
                    vehicle_id=vehicle.id,
                    path=path,
                    cost=cost,
                    priority_collected=priority_collected,
                    demands_served=demands_served,
                )
            ],
            edge_modifiers_applied=[],
            metadata={"mode": "single_vehicle_tsp"},
        )

    def _solve_multi_vehicle(
        self,
        payload: ProblemPayload,
        matrix: np.ndarray,
    ) -> SolveResponse:
        result = solve_cvrp_ortools(
            matrix,
            payload.vehicles,
            payload.target_nodes,
            time_limit_ms=settings.lkh_time_limit_ms,
            previous_routes=self._previous_routes or None,
        )

        priority_map = {t.id: t for t in payload.target_nodes}
        routes: list[RouteResult] = []
        for vehicle in payload.vehicles:
            path = result.routes.get(vehicle.id, [vehicle.start_node, vehicle.start_node])
            cost = tour_cost(matrix, path)
            priority = sum(priority_map[n].priority for n in path if n in priority_map)
            demands = sum(priority_map[n].demand for n in path if n in priority_map)
            routes.append(
                RouteResult(
                    vehicle_id=vehicle.id,
                    path=path,
                    cost=cost,
                    priority_collected=priority,
                    demands_served=demands,
                )
            )

        return SolveResponse(
            timestamp=datetime.now(timezone.utc),
            disaster_state=payload.disaster_state,
            solve_time_ms=0.0,
            solver_used=result.solver_used,
            total_cost=result.total_cost,
            total_priority=result.total_priority,
            routes=routes,
            edge_modifiers_applied=[],
            metadata={"mode": "multi_vehicle_cvrp"},
        )

    @classmethod
    def from_redis(cls, redis_client=None, **kwargs) -> SolverEngine:
        store = MatrixStore(redis_client) if redis_client is not None else None
        builder = CostMatrixBuilder(store)
        return cls(builder, **kwargs)

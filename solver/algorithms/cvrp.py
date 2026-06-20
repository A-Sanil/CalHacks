from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from solver.algorithms.nearest_neighbor import tour_cost
from solver.config import settings
from solver.core.schema import TargetNode, Vehicle


@dataclass
class CVRPSolution:
    routes: dict[str, list[int]]
    total_cost: float
    total_priority: float
    solver_used: str


def _build_priority_penalty(targets: list[TargetNode]) -> dict[int, float]:
    return {t.id: t.priority for t in targets}


def solve_cvrp_ortools(
    matrix: np.ndarray,
    vehicles: list[Vehicle],
    targets: list[TargetNode],
    *,
    time_limit_ms: int = 200,
    previous_routes: dict[str, list[int]] | None = None,
) -> CVRPSolution:
    """
    Multi-vehicle capacitated routing with priority rewards and time windows.
    Objective: maximize priority collected minus travel cost (scaled).
    """
    if not targets:
        return CVRPSolution(
            routes={v.id: [v.start_node, v.start_node] for v in vehicles},
            total_cost=0.0,
            total_priority=0.0,
            solver_used="ortools_empty",
        )

    # Single vehicle degenerates to prioritized TSP — handled upstream
    starts = [v.start_node for v in vehicles]
    ends = starts  # return to start depot
    manager = pywrapcp.RoutingIndexManager(
        matrix.shape[0],
        len(vehicles),
        starts,
        ends,
    )
    routing = pywrapcp.RoutingModel(manager)

    def transit_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        cost = matrix[from_node, to_node]
        if cost >= settings.blocked_cost / 2:
            return int(settings.blocked_cost)
        return int(round(cost * 1000))

    transit_idx = routing.RegisterTransitCallback(transit_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    target_by_id = {t.id: t for t in targets}
    priority_map = _build_priority_penalty(targets)

    def demand_callback(from_index: int) -> int:
        node = manager.IndexToNode(from_index)
        if node in target_by_id:
            return target_by_id[node].demand
        return 0

    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_idx,
        0,
        [v.capacity for v in vehicles],
        True,
        "Capacity",
    )

    # Time horizon must fit scaled arc costs (cost * 1000)
    max_horizon = int(matrix.max() * 1000 * (len(targets) + len(vehicles) + 2)) + 5000
    routing.AddDimension(
        transit_idx,
        0,
        max_horizon,
        False,
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    for v_idx in range(len(vehicles)):
        start_index = routing.Start(v_idx)
        end_index = routing.End(v_idx)
        time_dimension.CumulVar(start_index).SetRange(0, max_horizon)
        time_dimension.CumulVar(end_index).SetRange(0, max_horizon)

    for target in targets:
        index = manager.NodeToIndex(target.id)
        start, end = target.time_window
        time_dimension.CumulVar(index).SetRange(start, max(end, max_horizon))
        # Penalty for skipping: higher priority targets cheaper to skip
        penalty = int(round((100 - target.priority) * 1000))
        routing.AddDisjunction([index], penalty)

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params.time_limit.FromMilliseconds(time_limit_ms)

    solution = routing.SolveWithParameters(search_params)
    if solution is None:
        return CVRPSolution(
            routes={v.id: [v.start_node, v.start_node] for v in vehicles},
            total_cost=float("inf"),
            total_priority=0.0,
            solver_used="ortools_failed",
        )

    routes: dict[str, list[int]] = {}
    total_cost = 0.0
    total_priority = 0.0

    for v_idx, vehicle in enumerate(vehicles):
        path: list[int] = []
        index = routing.Start(v_idx)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            path.append(node)
            next_index = solution.Value(routing.NextVar(index))
            if not routing.IsEnd(next_index):
                to_node = manager.IndexToNode(next_index)
                total_cost += matrix[node, to_node]
            index = next_index
        end_node = manager.IndexToNode(index)
        path.append(end_node)
        routes[vehicle.id] = path

        for node in path:
            if node in priority_map:
                total_priority += priority_map[node]

    return CVRPSolution(
        routes=routes,
        total_cost=total_cost,
        total_priority=total_priority,
        solver_used="ortools_cvrp",
    )

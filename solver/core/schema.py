from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Vehicle(BaseModel):
    id: str
    type: str
    capacity: int = Field(ge=1)
    start_node: int = Field(ge=0)


class TargetNode(BaseModel):
    id: int = Field(ge=0)
    priority: float = Field(ge=0)
    demand: int = Field(ge=0)
    time_window: tuple[int, int]
    required: bool = False

    @field_validator("time_window")
    @classmethod
    def validate_window(cls, value: tuple[int, int]) -> tuple[int, int]:
        start, end = value
        if end < start:
            raise ValueError("time_window end must be >= start")
        return value


class DynamicEdgeModifier(BaseModel):
    edge: tuple[int, int]
    multiplier: float = Field(gt=0)
    reason: str = ""

    @field_validator("edge")
    @classmethod
    def validate_edge(cls, value: tuple[int, int]) -> tuple[int, int]:
        if len(value) != 2:
            raise ValueError("edge must be a pair of node ids")
        return value


class ProblemPayload(BaseModel):
    """JSON contract from the LLM agent (Step B)."""

    timestamp: datetime
    disaster_state: str
    vehicles: list[Vehicle] = Field(min_length=1)
    target_nodes: list[TargetNode] = Field(default_factory=list)
    dynamic_edge_modifiers: list[DynamicEdgeModifier] = Field(default_factory=list)
    # Nodes already visited during dynamic re-route — solver penalizes re-entry
    visited_nodes: list[int] = Field(default_factory=list)
    # Optional override when Redis is unavailable (tests / offline)
    baseline_matrix: list[list[float]] | None = None
    node_coords: list[tuple[float, float]] | None = None

    model_config = {"extra": "ignore"}


class RouteResult(BaseModel):
    vehicle_id: str
    path: list[int]
    cost: float
    priority_collected: float
    demands_served: int


class SolveResponse(BaseModel):
    timestamp: datetime
    disaster_state: str
    solve_time_ms: float
    solver_used: str
    total_cost: float
    total_priority: float
    routes: list[RouteResult]
    edge_modifiers_applied: list[DynamicEdgeModifier]
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dashboard_event(self) -> dict[str, Any]:
        """Wire format for the Mapbox dashboard WebSocket consumer."""
        return {
            "type": "route_update",
            "timestamp": self.timestamp.isoformat(),
            "disaster_state": self.disaster_state,
            "solve_time_ms": self.solve_time_ms,
            "solver_used": self.solver_used,
            "total_cost": self.total_cost,
            "total_priority": self.total_priority,
            "vehicles": [
                {
                    "id": route.vehicle_id,
                    "path": route.path,
                    "cost": route.cost,
                    "priority_collected": route.priority_collected,
                    "demands_served": route.demands_served,
                }
                for route in self.routes
            ],
            "edge_modifiers_applied": [
                {"edge": list(mod.edge), "multiplier": mod.multiplier, "reason": mod.reason}
                for mod in self.edge_modifiers_applied
            ],
            "node_coords": self.metadata.get("node_coords"),
            "target_nodes": self.metadata.get("target_nodes"),
            "metadata": self.metadata,
        }

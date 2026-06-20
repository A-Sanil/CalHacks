"""
your_solver_adapter.py  --  plugs the REAL SolverEngine into the Aegis loop.

solver_bridge.run_solver(store, adapter) calls adapter(contract, store) -> solution dict.
The heavy lifting lives in solver/adapters/aegis_contract.py.
"""
from __future__ import annotations

from typing import Any

from redis_store import AegisStore
from solver.adapters.aegis_contract import solve_contract


def adapter(contract: dict[str, Any], store: AegisStore) -> dict[str, Any]:
    """Aegis contract -> real CVRP/TSP solver -> Aegis solution."""
    return solve_contract(contract, store)

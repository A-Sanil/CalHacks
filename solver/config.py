from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    redis_url: str = os.getenv("AOE_REDIS_URL", "redis://localhost:6379/0")
    matrix_key: str = os.getenv("AOE_MATRIX_KEY", "aoe:distance_matrix")
    node_coords_key: str = os.getenv("AOE_NODE_COORDS_KEY", "aoe:node_coords")
    solver_host: str = os.getenv("AOE_SOLVER_HOST", "0.0.0.0")
    solver_port: int = int(os.getenv("AOE_SOLVER_PORT", "8000"))
    blocked_cost: float = float(os.getenv("AOE_BLOCKED_COST", "1e9"))
    ml_model_path: str = os.getenv("AOE_ML_MODEL_PATH", "models/warmstart.pt")
    use_ml_warmstart: bool = os.getenv("AOE_USE_ML_WARMSTART", "true").lower() == "true"
    lkh_time_limit_ms: int = int(os.getenv("AOE_LKH_TIME_LIMIT_MS", "500"))


settings = Settings()

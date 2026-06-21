from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

from solver.api.app import app
from solver.algorithms.ml_warmstart import TORCH_AVAILABLE, train_warmstart_model


def _payload() -> dict:
    n = 10
    rng = np.random.default_rng(1)
    coords = rng.random((n, 2)) * 50
    diff = coords[:, None, :] - coords[None, :, :]
    matrix = np.sqrt((diff ** 2).sum(axis=-1))
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disaster_state": "stable",
        "vehicles": [{"id": "V1", "type": "ground", "capacity": 15, "start_node": 0}],
        "target_nodes": [
            {"id": 2, "priority": 5.0, "demand": 1, "time_window": [0, 9999]},
            {"id": 5, "priority": 7.0, "demand": 2, "time_window": [0, 9999]},
        ],
        "dynamic_edge_modifiers": [],
        "baseline_matrix": matrix.tolist(),
        "node_coords": coords.tolist(),
    }


@pytest.fixture
def client():
    return TestClient(app)


class TestAPI:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_solve_endpoint(self, client):
        resp = client.post("/solve", json=_payload())
        assert resp.status_code == 200
        data = resp.json()
        assert "routes" in data
        assert data["routes"][0]["vehicle_id"] == "V1"
        assert data["solve_time_ms"] >= 0

    def test_dashboard_event_shape(self, client):
        resp = client.post("/solve", json=_payload())
        data = resp.json()
        assert "routes" in data
        from solver.core.schema import SolveResponse
        event = SolveResponse.model_validate(data).to_dashboard_event()
        assert event["type"] == "route_update"
        assert "vehicles" in event


class TestMLWarmstart:
    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch is an optional dependency")
    def test_train_and_predict(self, tmp_path):
        model_path = tmp_path / "warmstart.pt"
        model = train_warmstart_model(epochs=2, n_instances=5, n_nodes=8, output_path=str(model_path))
        assert model_path.exists()
        rng = np.random.default_rng(0)
        coords = rng.random((8, 2))
        diff = coords[:, None, :] - coords[None, :, :]
        matrix = np.sqrt((diff ** 2).sum(axis=-1))
        tour = model.predict_tour(coords, np.ones(8), matrix, 0, list(range(1, 8)))
        assert tour[0] == 0
        assert len(set(tour)) >= 4

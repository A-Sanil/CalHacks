from __future__ import annotations

from pathlib import Path

import numpy as np

from solver.config import settings

# torch is an OPTIONAL dependency. ML warm-start improves dynamic re-solves but is
# not required: when torch is unavailable we fall back to a nearest-neighbour rollout
# so the solver keeps working (and the whole package stays importable).
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only in torch-free environments
    torch = None  # type: ignore
    nn = None  # type: ignore
    F = None  # type: ignore
    TORCH_AVAILABLE = False


def _nearest_neighbour_tour(
    matrix: np.ndarray,
    start: int,
    nodes: list[int],
    *,
    return_to_start: bool = True,
) -> list[int]:
    """Deterministic NN rollout used directly as a fallback and as the ML teacher."""
    if not nodes:
        return [start, start] if return_to_start else [start]
    remaining = set(nodes)
    tour = [start]
    current = start
    while remaining:
        pick = min(remaining, key=lambda n: matrix[current, n])
        remaining.remove(pick)
        tour.append(pick)
        current = pick
    if return_to_start:
        tour.append(start)
    return tour


if TORCH_AVAILABLE:

    class WarmStartEncoder(nn.Module):
        """
        Lightweight pointer-style encoder that scores next-node choices.
        Used to warm-start NN tours before 2-opt / re-solve on dynamic updates.
        """

        def __init__(self, hidden_dim: int = 64) -> None:
            super().__init__()
            self.node_embed = nn.Linear(3, hidden_dim)  # x, y, priority
            self.edge_embed = nn.Linear(1, hidden_dim)  # normalized distance
            self.gru = nn.GRU(hidden_dim, hidden_dim, batch_first=True)
            self.pointer = nn.Linear(hidden_dim * 2, 1)

        def forward(self, node_feats, dist_row, mask):
            node_h = self.node_embed(node_feats)
            edge_h = self.edge_embed(dist_row)
            h = node_h + edge_h
            _, hidden = self.gru(h)
            query = hidden[-1].unsqueeze(1).expand(-1, h.size(1), -1)
            scores = self.pointer(torch.cat([query, h], dim=-1)).squeeze(-1)
            scores = scores.masked_fill(mask <= 0, -1e9)
            return scores

    class WarmStartModel:
        """Trainable warm-start policy with greedy rollout (torch backend)."""

        torch_backed = True

        def __init__(self, model_path: str | None = None) -> None:
            self.device = torch.device("cpu")
            self.net = WarmStartEncoder().to(self.device)
            self.model_path = Path(model_path or settings.ml_model_path)
            if self.model_path.exists():
                self.net.load_state_dict(torch.load(self.model_path, map_location=self.device))
            self.net.eval()

        def save(self) -> None:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(self.net.state_dict(), self.model_path)

        def predict_tour(self, coords, priorities, matrix, start, nodes, *, return_to_start=True):
            if not nodes:
                return [start, start] if return_to_start else [start]

            remaining = set(nodes)
            tour = [start]
            current = start

            while remaining:
                node_list = sorted(remaining | {current})
                feats = []
                for n in node_list:
                    x, y = coords[n]
                    p = priorities[n] if n < len(priorities) else 0.0
                    feats.append([x, y, p / 10.0])
                node_feats = torch.tensor([feats], dtype=torch.float32, device=self.device)

                dists, mask = [], []
                for n in node_list:
                    dists.append([matrix[current, n] / (matrix.max() + 1e-6)])
                    mask.append(1.0 if n in remaining else 0.0)
                dist_row = torch.tensor([dists], dtype=torch.float32, device=self.device)
                mask_t = torch.tensor([mask], dtype=torch.float32, device=self.device)

                with torch.no_grad():
                    scores = self.net(node_feats, dist_row, mask_t)
                    pick = node_list[int(scores[0, : len(node_list)].argmax().item())]
                    if pick not in remaining:
                        pick = min(remaining, key=lambda n: matrix[current, n])
                remaining.remove(pick)
                tour.append(pick)
                current = pick

            if return_to_start:
                tour.append(start)
            return tour

else:

    class WarmStartModel:
        """Fallback warm-start (no torch): nearest-neighbour rollout."""

        torch_backed = False

        def __init__(self, model_path: str | None = None) -> None:
            self.model_path = Path(model_path or settings.ml_model_path)

        def save(self) -> None:  # pragma: no cover - nothing to persist
            pass

        def predict_tour(self, coords, priorities, matrix, start, nodes, *, return_to_start=True):
            return _nearest_neighbour_tour(matrix, start, nodes, return_to_start=return_to_start)


def ensure_warmstart_model(*, epochs=40, n_instances=150, n_nodes=16, output_path=None) -> WarmStartModel:
    """Load trained weights or train a lightweight model if missing (NN fallback if no torch)."""
    path = Path(output_path or settings.ml_model_path)
    if TORCH_AVAILABLE and not path.exists():
        train_warmstart_model(epochs=epochs, n_instances=n_instances, n_nodes=n_nodes, output_path=str(path))
    return WarmStartModel(str(path))


def train_warmstart_model(epochs=50, n_instances=200, n_nodes=12, seed=42, output_path=None) -> WarmStartModel:
    """Self-supervised training (imitate NN tours). Requires torch."""
    if not TORCH_AVAILABLE:
        raise RuntimeError(
            "train_warmstart_model requires torch. Install torch, or use the "
            "nearest-neighbour fallback (set AOE_USE_ML_WARMSTART=false)."
        )
    rng = np.random.default_rng(seed)
    model = WarmStartModel(model_path=output_path)
    model.net.train()
    optimizer = torch.optim.Adam(model.net.parameters(), lr=1e-3)

    for _ in range(epochs):
        for _ in range(n_instances):
            coords = rng.random((n_nodes, 2))
            diff = coords[:, None, :] - coords[None, :, :]
            matrix = np.sqrt((diff ** 2).sum(axis=-1))
            priorities = rng.random(n_nodes) * 10

            start = 0
            remaining = set(range(1, n_nodes))
            current = start
            while remaining:
                node_list = sorted(remaining | {current})
                feats = [[coords[n, 0], coords[n, 1], priorities[n] / 10.0] for n in node_list]
                node_feats = torch.tensor([feats], dtype=torch.float32)
                dists = [[matrix[current, n] / (matrix.max() + 1e-6)] for n in node_list]
                dist_row = torch.tensor([dists], dtype=torch.float32)
                mask = torch.tensor([[1.0 if n in remaining else 0.0 for n in node_list]], dtype=torch.float32)

                scores = model.net(node_feats, dist_row, mask)
                nn_pick = min(remaining, key=lambda n: matrix[current, n])
                target_idx = node_list.index(nn_pick)
                loss = F.cross_entropy(scores, torch.tensor([target_idx]))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                remaining.remove(nn_pick)
                current = nn_pick

    model.net.eval()
    model.save()
    return model

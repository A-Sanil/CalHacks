from __future__ import annotations

import argparse

from solver.algorithms.ml_warmstart import ensure_warmstart_model, train_warmstart_model
from solver.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ML warm-start model for dynamic re-routing")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--instances", type=int, default=200)
    parser.add_argument("--nodes", type=int, default=16)
    parser.add_argument("--output", default=settings.ml_model_path)
    parser.add_argument("--ensure", action="store_true", help="Train only if model file is missing")
    args = parser.parse_args()

    if args.ensure:
        model = ensure_warmstart_model(
            epochs=args.epochs,
            n_instances=args.instances,
            n_nodes=args.nodes,
            output_path=args.output,
        )
        print(f"Model ready at {model.model_path}")
    else:
        model = train_warmstart_model(
            epochs=args.epochs,
            n_instances=args.instances,
            n_nodes=args.nodes,
            output_path=args.output,
        )
        print(f"Trained model saved to {model.model_path}")


if __name__ == "__main__":
    main()

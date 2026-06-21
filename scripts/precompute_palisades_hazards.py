"""Precompute exact route/fire intersections for the historical browser replay."""

import json
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.prepared import prep
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "palisades"


def main() -> None:
    graph = json.loads((DATA / "road_graph_25.json").read_text(encoding="utf-8"))
    timeline = json.loads((DATA / "fire_timeline.geojson").read_text(encoding="utf-8"))
    matrix: dict[str, dict[str, list]] = {}
    first_exposure: dict[str, int] = {}

    fire_history = []
    for snapshot_index, feature in enumerate(timeline["features"]):
        fire_history.append(shape(feature["geometry"]))
        fire_geometry = unary_union(fire_history)
        fire = prep(fire_geometry)
        blocked = []
        for edge in graph["edges"]:
            route = {"type": "LineString", "coordinates": edge["path"]}
            if fire.intersects(shape(route)):
                route_key = f'{edge["source"]}:{edge["target"]}'
                blocked.append(route_key)
                first_exposure.setdefault(route_key, snapshot_index)
        consumed_sites = [
            node["id"]
            for node in graph["nodes"]
            if fire.intersects(Point(node["longitude"], node["latitude"]))
        ]
        node_distances_km = {
            str(node["id"]): round(fire_geometry.distance(Point(node["longitude"], node["latitude"])) * 111.0, 3)
            for node in graph["nodes"]
        }
        matrix[feature["properties"]["timestamp"]] = {
            "blocked_routes": blocked,
            "route_exposure_steps": {route_key: snapshot_index - first_exposure[route_key] + 1 for route_key in blocked},
            "consumed_sites": consumed_sites,
            "node_distances_km": node_distances_km,
        }

    output = DATA / "hazard_route_matrix.json"
    output.write_text(json.dumps(matrix, separators=(",", ":")), encoding="utf-8")
    intersections = sum(len(snapshot["blocked_routes"]) for snapshot in matrix.values())
    print(f"Wrote {output} ({len(matrix)} snapshots, {intersections} cumulative intersections)")


if __name__ == "__main__":
    main()

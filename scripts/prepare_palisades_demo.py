"""Normalize Palisades Fire source data into deterministic demo artifacts."""
from __future__ import annotations

import heapq
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "palisades"
OUT = ROOT / "data" / "processed" / "palisades"
OUT.mkdir(parents=True, exist_ok=True)

DEMO_BBOX = (-118.72, 33.99, -118.46, 34.16)
HIGHWAY_SPEED_KPH = {
    "motorway": 90, "trunk": 70, "primary": 55, "secondary": 45,
    "tertiary": 38, "residential": 28, "unclassified": 25,
    "service": 18, "living_street": 15,
}


def iso_millis(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def normalize_fire() -> None:
    data = json.loads((RAW / "fire_progression_lafd.geojson").read_text(encoding="utf-8"))
    features = sorted(data["features"], key=lambda feature: feature["properties"]["PROG_DATETIME"])
    for index, feature in enumerate(features):
        props = feature["properties"]
        props["timeline_index"] = index
        props["timestamp"] = iso_millis(props["PROG_DATETIME"])
        props["source"] = "Los Angeles Fire Department"
    output = {"type": "FeatureCollection", "features": features}
    (OUT / "fire_timeline.geojson").write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")


def normalize_smoke() -> None:
    records = []
    west, south, east, north = (-119.5, 33.5, -117.5, 34.6)
    for path in sorted(RAW.glob("airnow_2025*.dat")):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split("|")
            if len(parts) < 13 or parts[3] != "PM2.5-24hr":
                continue
            try:
                value = float(parts[5]); lat = float(parts[10]); lon = float(parts[11])
            except ValueError:
                continue
            if value < 0 or not (west <= lon <= east and south <= lat <= north):
                continue
            records.append({
                "date": datetime.strptime(parts[0], "%m/%d/%y").date().isoformat(),
                "station_id": parts[1], "station_name": parts[2], "pm25_ug_m3": value,
                "aqi": None if parts[8] in ("", "-999") else float(parts[8]),
                "latitude": lat, "longitude": lon, "agency": parts[7],
            })
    (OUT / "smoke_pm25_timeline.json").write_text(json.dumps(records, indent=2), encoding="utf-8")


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a); lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 12_742_000 * math.asin(math.sqrt(h))


def largest_component(adjacency: dict[int, list[tuple[int, float, float]]]) -> set[int]:
    unseen = set(adjacency)
    largest: set[int] = set()
    while unseen:
        start = unseen.pop(); component = {start}; stack = [start]
        while stack:
            node = stack.pop()
            for neighbor, _, _ in adjacency.get(node, []):
                if neighbor in unseen:
                    unseen.remove(neighbor); component.add(neighbor); stack.append(neighbor)
        if len(component) > len(largest): largest = component
    return largest


def select_sites(candidates: list[int], coords: dict[int, tuple[float, float]], count: int) -> list[int]:
    center = (34.075, -118.595)
    selected = [min(candidates, key=lambda node: haversine_m(coords[node], center))]
    while len(selected) < count:
        selected.append(max(
            (node for node in candidates if node not in selected),
            key=lambda node: min(haversine_m(coords[node], coords[pick]) for pick in selected),
        ))
    return selected


def dijkstra(start: int, adjacency: dict[int, list[tuple[int, float, float]]]):
    distances = {start: 0.0}; previous: dict[int, int] = {}; queue = [(0.0, start)]
    while queue:
        cost, node = heapq.heappop(queue)
        if cost != distances.get(node): continue
        for neighbor, minutes, _ in adjacency[node]:
            candidate = cost + minutes
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate; previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))
    return distances, previous


def normalize_roads() -> None:
    raw = json.loads((RAW / "roads_osm_overpass.json").read_text(encoding="utf-8"))
    coords = {item["id"]: (item["lat"], item["lon"]) for item in raw["elements"] if item["type"] == "node"}
    adjacency: dict[int, list[tuple[int, float, float]]] = {}
    road_features = []
    for item in raw["elements"]:
        if item["type"] != "way" or "highway" not in item.get("tags", {}): continue
        node_ids = [node for node in item.get("nodes", []) if node in coords]
        if len(node_ids) < 2: continue
        highway = item["tags"]["highway"]
        speed = HIGHWAY_SPEED_KPH.get(highway, 22)
        line = [[coords[node][1], coords[node][0]] for node in node_ids]
        road_features.append({"type":"Feature","properties":{"osm_id":item["id"],"highway":highway,"name":item.get("tags",{}).get("name")},"geometry":{"type":"LineString","coordinates":line}})
        for left, right in zip(node_ids, node_ids[1:]):
            distance = haversine_m(coords[left], coords[right]); minutes = distance / (speed * 1000 / 60)
            adjacency.setdefault(left, []).append((right, minutes, distance))
            adjacency.setdefault(right, []).append((left, minutes, distance))

    component = largest_component(adjacency)
    adjacency = {node: [(n, t, d) for n, t, d in edges if n in component] for node, edges in adjacency.items() if node in component}
    candidates = [node for node, edges in adjacency.items() if len(edges) >= 3]
    selected = select_sites(candidates, coords, 25)
    selected_index = {node: index for index, node in enumerate(selected)}
    nodes = [{"id": index, "osm_id": node, "latitude": coords[node][0], "longitude": coords[node][1]} for node, index in selected_index.items()]
    edges = []
    for source in selected:
        distances, previous = dijkstra(source, adjacency)
        for target in selected:
            if source == target: continue
            path = [target]
            while path[0] != source: path.insert(0, previous[path[0]])
            distance_m = sum(haversine_m(coords[a], coords[b]) for a, b in zip(path, path[1:]))
            edges.append({
                "source": selected_index[source], "target": selected_index[target],
                "base_time_min": round(distances[target], 3), "distance_m": round(distance_m, 1),
                "path": [[coords[node][1], coords[node][0]] for node in path],
            })
    graph = {"bbox": DEMO_BBOX, "node_count": len(nodes), "directed_edge_count": len(edges), "nodes": nodes, "edges": edges}
    (OUT / "road_graph_25.json").write_text(json.dumps(graph, separators=(",", ":")), encoding="utf-8")
    (OUT / "roads_display.geojson").write_text(json.dumps({"type":"FeatureCollection","features":road_features}, separators=(",", ":")), encoding="utf-8")


def build_replay_timeline() -> None:
    fire = json.loads((OUT / "fire_timeline.geojson").read_text(encoding="utf-8"))
    smoke = json.loads((OUT / "smoke_pm25_timeline.json").read_text(encoding="utf-8"))
    graph = json.loads((OUT / "road_graph_25.json").read_text(encoding="utf-8"))
    events = []
    for feature in fire["features"]:
        events.append({"timestamp": feature["properties"]["timestamp"], "type": "fire_perimeter", "source": "LAFD", "payload": feature})
    by_date: dict[str, list[dict]] = {}
    for record in smoke: by_date.setdefault(record["date"], []).append(record)
    for day, records in by_date.items():
        events.append({"timestamp": f"{day}T20:00:00+00:00", "type": "smoke_observation", "source": "EPA AirNow", "payload": records})
    rng = random.Random(20250107)
    candidates = [node for node in graph["nodes"] if node["id"] not in (0,)]
    for index, fire_feature_index in enumerate((2, 5, 8), start=1):
        node = rng.choice(candidates)
        events.append({
            "timestamp": fire["features"][fire_feature_index]["properties"]["timestamp"],
            "type": "sar_request", "source": "demo_scenario", "synthetic": True,
            "payload": {"id": f"SAR-{index:02d}", "node_id": node["id"], "latitude": node["latitude"], "longitude": node["longitude"], "priority": 7 + index, "people": index + 1},
        })
    events.sort(key=lambda event: event["timestamp"])
    (OUT / "replay_timeline.json").write_text(json.dumps(events, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    normalize_fire(); normalize_smoke(); normalize_roads(); build_replay_timeline()
    print(f"Prepared Palisades data in {OUT}")


if __name__ == "__main__":
    main()

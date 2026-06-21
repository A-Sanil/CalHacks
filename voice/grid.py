"""
grid.py -- military-style coordinate grid <-> lat/lng for the Palisades AO.

The dashboard shows a coordinate grid; dispatchers think in grid squares
('echo five'), not decimal degrees. This module is the translation layer so a
spoken 'grid E5' becomes a real lat/lng node the solver can route to, and any
node's lat/lng can be reported back as a grid square.

Grid:  columns A..H (west -> east)  x  rows 1..8 (north -> south)  = 64 squares.
Box matches the seeded Palisades graph extents (graph_seed lat/lng), padded.
"""
from __future__ import annotations

import math
import re
import string
from typing import List, Optional, Tuple

# Operating area (Palisades). South/North lat, West/East lng.
LAT_MIN, LAT_MAX = 37.00, 37.11
LNG_MIN, LNG_MAX = -122.11, -122.00
N_COLS, N_ROWS = 8, 8                 # A..H x 1..8  -> 'E5' is valid
COST_PER_DEGREE = 150.0               # scale geographic distance -> graph cost
MIN_EDGE_COST = 1.0

_COLS = string.ascii_uppercase[:N_COLS]            # 'ABCDEFGH'
_PHONETIC = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliet": "J",
}
_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


# ---- parsing ---------------------------------------------------------------
def find_grid_ref(text: str) -> Optional[str]:
    """Pull a grid square out of free speech.
    Handles 'E5', 'e-5', 'E 5', 'echo five', 'grid echo 5', 'square E5'."""
    t = text.lower()
    # phonetic word + number-word/digit  e.g. 'echo five', 'echo 5'
    for word, letter in _PHONETIC.items():
        m = re.search(word + r"[\s,-]*([0-9]+|" + "|".join(_WORD_NUM) + r")", t)
        if m:
            num = m.group(1)
            n = _WORD_NUM.get(num, None) or (int(num) if num.isdigit() else None)
            if n:
                return f"{letter}{n}"
    # letter + digit  e.g. 'E5', 'e-5', 'grid e 5'
    m = re.search(r"\b([a-h])\s*-?\s*([1-8])\b", t)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    return None


def parse_grid_ref(ref: str) -> Tuple[int, int]:
    """'E5' -> (col_idx, row_idx), both 0-based. Raises on garbage."""
    ref = ref.strip().upper().replace(" ", "").replace("-", "")
    m = re.match(r"^([A-Z])([0-9]{1,2})$", ref)
    if not m:
        raise ValueError(f"bad grid ref: {ref!r}")
    col = _COLS.find(m.group(1))
    row = int(m.group(2)) - 1
    if col < 0 or not (0 <= row < N_ROWS):
        raise ValueError(f"grid ref out of range: {ref!r}")
    return col, row


# ---- conversion ------------------------------------------------------------
def grid_to_latlng(ref: str) -> Tuple[float, float]:
    """Grid square -> (lat, lng) at the square's centre."""
    col, row = parse_grid_ref(ref)
    lng = LNG_MIN + (col + 0.5) / N_COLS * (LNG_MAX - LNG_MIN)
    lat = LAT_MAX - (row + 0.5) / N_ROWS * (LAT_MAX - LAT_MIN)  # row0 = north
    return round(lat, 5), round(lng, 5)


def latlng_to_grid(lat: float, lng: float) -> str:
    """(lat, lng) -> nearest grid square label, clamped to the box."""
    col = int((lng - LNG_MIN) / (LNG_MAX - LNG_MIN) * N_COLS)
    row = int((LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * N_ROWS)
    col = max(0, min(N_COLS - 1, col))
    row = max(0, min(N_ROWS - 1, row))
    return f"{_COLS[col]}{row + 1}"


def _dist_deg(lat1, lng1, lat2, lng2) -> float:
    """Cheap planar distance in degrees (fine at AO scale)."""
    return math.hypot(lat1 - lat2, lng1 - lng2)


def edge_cost(lat1, lng1, lat2, lng2) -> float:
    """Geographic distance -> graph cost unit, comparable to seeded edges."""
    return round(max(MIN_EDGE_COST, _dist_deg(lat1, lng1, lat2, lng2) * COST_PER_DEGREE), 1)


def nearest_nodes(store, lat: float, lng: float, k: int = 3,
                  exclude_types: Tuple[str, ...] = ("fire",)) -> List[Tuple[int, float]]:
    """k nearest existing graph nodes to (lat,lng): list of (node_id, dist_deg)."""
    out = []
    for nid in store.all_node_ids():
        n = store.get_node(nid)
        if not n:
            continue
        if n.get("type") in exclude_types:
            continue
        try:
            nlat, nlng = float(n["lat"]), float(n["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append((nid, _dist_deg(lat, lng, nlat, nlng)))
    out.sort(key=lambda x: x[1])
    return out[:k]

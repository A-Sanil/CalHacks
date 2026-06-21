"""
voice_intake.py -- turn a spoken 911 call into a NEW search-and-rescue target on
the live dashboard grid, then let the real OR-Tools solver route to it.

    browser mic  ->  audio bytes  ->  Deepgram STT (nova-3, key stays SERVER-side)
                 ->  transcript   ->  parse grid ref + #victims + priority
                 ->  new TargetNode on the 24-node tactical grid
                 ->  /optimize re-solves  ->  a vehicle is dispatched to the site.

Everything degrades gracefully (the Aegis house style):
  * no DEEPGRAM_API_KEY        -> dispatcher can TYPE the transcript instead
  * transcript has no grid ref -> drop the site on the nearest free grid node
  * 'critical'                 -> node is marked required, so it is guaranteed
                                  served (the live-reroute money shot)
"""
from __future__ import annotations

import os
import re
from typing import Optional

from ..core.schema import ProblemPayload, TargetNode
from . import frontend_graph as fg

# ----------------------------------------------------------------------------- grid
# The dashboard grid is 6 columns (A-F, left->right) x 4 rows (1-4, top->bottom),
# laid out row-major in NODE_XY, so node_id = (row-1)*6 + col_index.
GRID_COLS = "ABCDEF"
GRID_ROWS = (1, 2, 3, 4)
_N_COLS = len(GRID_COLS)

NATO = {
    "alpha": "A", "alfa": "A", "bravo": "B", "charlie": "C",
    "delta": "D", "echo": "E", "foxtrot": "F", "fox": "F",
}
_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4,
    # frequent STT homophones for 1-4
    "won": 1, "to": 2, "too": 2, "tree": 3, "for": 4, "fore": 4,
}

# broader number words for counting victims (rows only need 1-4; demand can be more)
_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "twentyone": 21, "twenty-one": 21,
    "twentytwo": 22, "twenty-two": 22, "twentythree": 23, "twenty-three": 23,
    "twentyfour": 24, "twenty-four": 24,
    "a": 1, "an": 1, "couple": 2, "few": 3, "several": 4, "dozen": 12,
}
# priority label -> (reward weight, is_required)
PRIORITY = {
    "critical": (5.0, True), "life-threatening": (5.0, True), "mayday": (5.0, True),
    "code red": (5.0, True), "trapped": (5.0, True),
    "high": (4.0, False), "urgent": (4.0, False), "serious": (4.0, False),
    "medium": (3.0, False), "moderate": (3.0, False),
    "low": (2.0, False), "minor": (2.0, False),
}
_DEFAULT_PRIORITY = ("high", 4.0, False)


class VoiceIntakeError(RuntimeError):
    """Raised when audio can't be turned into a transcript (e.g. no API key)."""


def grid_to_node(col_letter: str, row: int) -> Optional[int]:
    col_letter = (col_letter or "").upper()
    if col_letter not in GRID_COLS or row not in GRID_ROWS:
        return None
    nid = (row - 1) * _N_COLS + GRID_COLS.index(col_letter)
    return nid if 0 <= nid < len(fg.NODE_XY) else None


def node_to_grid(node_id: int) -> str:
    row, col = divmod(int(node_id), _N_COLS)
    if 0 <= col < _N_COLS and 0 <= row < len(GRID_ROWS):
        return GRID_COLS[col] + str(row + 1)
    return "?" + str(node_id)


def parse_grid_ref(text: str) -> Optional[str]:
    """Pull a grid ref out of free text. Accepts 'E2', 'e-2', 'e 2',
    'grid echo two', 'echo 2', 'echo-two'."""
    t = " " + text.lower() + " "
    # 1) compact alphanumeric: e2 / e-2 / e 2
    m = re.search(r"[^a-z]([a-f])[\s\-]?([1-4])(?![0-9])", t)
    if m:
        return m.group(1).upper() + m.group(2)
    # 2) phonetic: 'echo two', 'bravo 3', 'delta-four'
    nato = "|".join(NATO)
    nums = "|".join(list(_WORD_NUM) + [str(n) for n in GRID_ROWS])
    m = re.search(rf"\b({nato})[\s\-]+({nums})\b", t)
    if m:
        col = NATO[m.group(1)]
        raw = m.group(2)
        row = int(raw) if raw.isdigit() else _WORD_NUM.get(raw)
        if row in GRID_ROWS:
            return col + str(row)
    return None


def parse_priority(text: str):
    """Return (label, weight, required) -- highest severity mentioned wins."""
    t = text.lower()
    best = None
    for word, (weight, req) in PRIORITY.items():
        if word in t:
            if best is None or weight > best[1]:
                best = (word, weight, req)
    return best or _DEFAULT_PRIORITY


_VICTIM_WORDS = r"(?:victim|people|persons?|trapped|evacuees?|civilians?|souls?|injured|patients?)"


def parse_demand(text: str) -> int:
    """How many people? '2 victims', 'two trapped', 'family of four',
    'couple of people', 'a dozen'. Default 1."""
    t = text.lower()
    words = "|".join(sorted(_NUM_WORDS, key=len, reverse=True))
    pats = [
        rf"(\d+|{words})\s+(?:\w+\s+)?{_VICTIM_WORDS}",   # 'six (people) inside'
        rf"{_VICTIM_WORDS}[^.\d]*?(\d+|{words})",          # 'victims: 3'
        rf"family of (\d+|{words})",                       # 'family of four'
    ]
    for p in pats:
        m = re.search(p, t)
        if m:
            raw = m.group(1)
            n = int(raw) if raw.isdigit() else _NUM_WORDS.get(raw, 1)
            return max(1, min(n, 99))
    return 1


def parse_node_id(text: str, max_node: int = 24):
    """Pull an explicit map node out of '...node twelve', 'site 7', 'sector N12',
    'grid twenty-one'. Returns an int in [0, max_node] or None. Used by the
    Palisades dashboard, whose markers are labelled N0..N24."""
    t = text.lower()
    words = "|".join(sorted(_NUM_WORDS, key=len, reverse=True))
    m = re.search(rf"\b(?:node|site|sector|grid|sar)\s+n?\.?\s*(\d+|{words})\b", t)
    if not m:
        m = re.search(r"\bn[\s\.\-]?(\d{1,2})\b", t)
    if m:
        raw = m.group(1)
        n = int(raw) if raw.isdigit() else _NUM_WORDS.get(raw)
        if n is not None and 0 <= n <= max_node:
            return n
    return None


def _nearest_free_node(occupied: set[int]) -> int:
    """Fallback when no grid ref is spoken: first grid node that is not a depot
    and not already a target."""
    for nid in range(len(fg.NODE_XY)):
        if nid not in occupied:
            return nid
    return 0


def parse_911(transcript: str, occupied: Optional[set[int]] = None) -> dict:
    """transcript -> structured SAR site on the dashboard grid."""
    occupied = set(occupied or ())
    grid = parse_grid_ref(transcript)
    node_id = grid_to_node(grid[0], int(grid[1])) if grid else None
    if node_id is None:
        node_id = _nearest_free_node(occupied)
        grid = node_to_grid(node_id)
        grid_source = "fallback"
    else:
        grid_source = "spoken"
    label, weight, required = parse_priority(transcript)
    demand = parse_demand(transcript)
    return {
        "node_id": node_id,
        "grid": grid,
        "grid_source": grid_source,
        "demand": demand,
        "priority": weight,
        "priority_label": label,
        "required": required,
    }


# ----------------------------------------------------------------------------- STT
def _api_key() -> Optional[str]:
    key = os.environ.get("DEEPGRAM_API_KEY")
    if key:
        return key
    # best-effort .env load (repo root), so the key works without exporting it
    here = os.path.dirname(__file__)
    root = os.path.abspath(os.path.join(here, "..", ".."))
    path = os.path.join(root, ".env")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEEPGRAM_API_KEY=") and "=" in line:
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if v:
                            os.environ.setdefault("DEEPGRAM_API_KEY", v)
                            return v
        except OSError:
            pass
    return None


def transcribe_audio(buf: bytes, mimetype: Optional[str] = None,
                     *, model: str = "nova-3", timeout: float = 30.0):
    """Raw audio bytes -> (transcript, source) via Deepgram's pre-recorded REST
    API. Key stays server-side. Raises VoiceIntakeError if no key is configured."""
    key = _api_key()
    if not key:
        raise VoiceIntakeError(
            "DEEPGRAM_API_KEY not set -- type the 911 transcript instead."
        )
    import httpx

    params = {
        "model": model, "smart_format": "true", "punctuate": "true",
        "keyterm": list(NATO) + ["grid", "victims", "trapped", "critical", "evacuees"],
    }
    headers = {"Authorization": "Token " + key,
               "Content-Type": mimetype or "audio/webm"}
    resp = httpx.post("https://api.deepgram.com/v1/listen",
                      params=params, headers=headers, content=buf, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    text = (
        data.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("transcript", "")
    )
    return text, "deepgram:" + model


# ----------------------------------------------------------------------------- intake
def process_intake(transcript: str, payload: ProblemPayload):
    """Append the parsed SAR site to payload.target_nodes (in place on a copy)
    and return (added_meta, new_payload) ready to feed straight into /optimize."""
    occupied = {t.id for t in payload.target_nodes}
    occupied |= {v.start_node for v in payload.vehicles}  # don't drop a site on a depot
    parsed = parse_911(transcript, occupied=occupied)

    node = TargetNode(
        id=parsed["node_id"],
        priority=parsed["priority"],
        demand=parsed["demand"],
        time_window=(0, 480),
        required=parsed["required"],
    )
    # copy so we never mutate the caller's request
    new_targets = [t for t in payload.target_nodes if t.id != node.id] + [node]
    new_payload = payload.model_copy(update={"target_nodes": new_targets})
    return parsed, new_payload
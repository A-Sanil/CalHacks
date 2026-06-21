"""
optimize.py  --  /optimize endpoint: the dashboard's live solve path.

Accepts the frontend OptimizationRequest (a subset of ProblemPayload, sans matrix),
builds a LIVE cost matrix on the 24-node tactical grid (frontend_graph) with the
request's dynamic_edge_modifiers applied, runs the REAL SolverEngine (OR-Tools
CVRP), and returns OptimizedRoute[] with ordered_nodes + svg_path drawn on that
same grid so the map renders the true road paths the solver chose.

Mirrors solver/adapters/aegis_contract.py: matrix supplied inline via
baseline_matrix, dynamic_edge_modifiers emptied (weights already baked in).
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from solver.api import frontend_graph as fg
from solver.api import voice_intake as vi
from solver.core.schema import ProblemPayload
from solver.core.solver import SolverEngine

router = APIRouter()


class OptimizedRoute(BaseModel):
    vehicle_id: str
    ordered_nodes: list[int]
    svg_path: str
    eta_minutes: float
    priority_served: float


class OptimizationMetrics(BaseModel):
    people_routed: int
    total_priority_served: float


class OptimizationResult(BaseModel):
    generated_at: str
    solve_time_ms: float
    routes: list[OptimizedRoute]
    metrics: OptimizationMetrics


_engine: SolverEngine | None = None


def get_engine() -> SolverEngine:
    global _engine
    if _engine is None:
        _engine = SolverEngine.from_redis(None)
    return _engine


@router.post("/optimize", response_model=OptimizationResult)
async def optimize(request: ProblemPayload) -> OptimizationResult:
    """Solve on the live tactical grid and return map-ready routes."""
    # 1) live adjacency with edge modifiers applied; all-pairs for matrix + paths
    adj = fg.live_adjacency(request.dynamic_edge_modifiers)
    matrix = fg.cost_matrix(adj)
    _dist, prevs = fg.all_pairs(adj)
    coords = fg.node_coords()

    # 2) rebuild payload with the live matrix baked in (modifiers already applied)
    payload = ProblemPayload(
        timestamp=request.timestamp,
        disaster_state=request.disaster_state,
        vehicles=request.vehicles,
        target_nodes=request.target_nodes,
        dynamic_edge_modifiers=[],
        visited_nodes=request.visited_nodes,
        baseline_matrix=matrix,
        node_coords=[tuple(c) for c in coords],
    )

    # 3) run the REAL solver
    response = get_engine().solve(payload)

    # 4) map RouteResult -> OptimizedRoute, expanding waypoints into full road paths
    routes: list[OptimizedRoute] = []
    people = 0
    prio = 0.0
    for r in response.routes:
        ordered = fg.expand_waypoints(list(r.path), prevs)
        routes.append(
            OptimizedRoute(
                vehicle_id=r.vehicle_id,
                ordered_nodes=ordered,
                svg_path=fg.svg_path(ordered),
                eta_minutes=round(float(r.cost), 1),
                priority_served=round(float(r.priority_collected), 2),
            )
        )
        people += int(r.demands_served)
        prio += float(r.priority_collected)

    return OptimizationResult(
        generated_at=response.timestamp.isoformat(),
        solve_time_ms=round(float(response.solve_time_ms), 2),
        routes=routes,
        metrics=OptimizationMetrics(
            people_routed=people,
            total_priority_served=round(prio, 2),
        ),
    )


# ============================================================================
# Voice intake: a spoken 911 call -> a new SAR site -> the solver routes to it.
# This is the live-demo money shot. Mic audio is transcribed SERVER-side
# (Deepgram key never reaches the browser); the typed path needs no key at all.
# ============================================================================
class VoiceIntakeRequest(BaseModel):
    """Typed / already-transcribed path (also what the demo's text box posts)."""
    transcript: str
    request: ProblemPayload


class AddedSite(BaseModel):
    node_id: int
    grid: str
    grid_source: str          # "spoken" | "fallback"
    demand: int
    priority: float
    priority_label: str
    required: bool
    served: bool              # did the solver actually route to it?
    served_by: str | None     # vehicle id that picked it up


class VoiceIntakeResult(BaseModel):
    transcript: str
    transcript_source: str    # "typed" | "deepgram:nova-3"
    added: AddedSite
    result: OptimizationResult


def _mark_served(added: dict, result: OptimizationResult) -> AddedSite:
    served_by = None
    for r in result.routes:
        if added["node_id"] in r.ordered_nodes:
            served_by = r.vehicle_id
            break
    return AddedSite(served=served_by is not None, served_by=served_by, **added)


async def _run_intake(transcript: str, source: str,
                      payload: ProblemPayload) -> VoiceIntakeResult:
    added, new_payload = vi.process_intake(transcript, payload)
    result = await optimize(new_payload)          # reuse the real solve path
    return VoiceIntakeResult(
        transcript=transcript,
        transcript_source=source,
        added=_mark_served(added, result),
        result=result,
    )


@router.post("/voice/intake", response_model=VoiceIntakeResult)
async def voice_intake(body: VoiceIntakeRequest) -> VoiceIntakeResult:
    """Transcript -> new SAR target -> re-solve. No API key required."""
    return await _run_intake(body.transcript.strip(), "typed", body.request)


@router.post("/voice/intake/audio", response_model=VoiceIntakeResult)
async def voice_intake_audio(
    audio: UploadFile = File(...),
    request: str = Form(...),
) -> VoiceIntakeResult:
    """Mic audio -> Deepgram STT (server-side) -> new SAR target -> re-solve."""
    try:
        payload = ProblemPayload.model_validate_json(request)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"bad request payload: {exc}")
    buf = await audio.read()
    try:
        transcript, source = vi.transcribe_audio(buf, audio.content_type)
    except vi.VoiceIntakeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001  (Deepgram/network error)
        raise HTTPException(status_code=502, detail=f"transcription failed: {exc}")
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="empty transcript from audio")
    return await _run_intake(transcript.strip(), source, payload)


class TranscribeResult(BaseModel):
    transcript: str
    source: str               # "deepgram:nova-3"
    node_hint: int | None     # parsed map node (N0..N24) if the caller named one


@router.post("/voice/transcribe", response_model=TranscribeResult)
async def voice_transcribe(audio: UploadFile = File(...)) -> TranscribeResult:
    """Mic audio -> Deepgram STT (server-side key). Returns the raw transcript so
    the dashboard can drop a new SAR site on whichever graph it renders."""
    buf = await audio.read()
    try:
        text, source = vi.transcribe_audio(buf, audio.content_type)
    except vi.VoiceIntakeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"transcription failed: {exc}")
    if not text.strip():
        raise HTTPException(status_code=422, detail="empty transcript from audio")
    return TranscribeResult(transcript=text, source=source,
                            node_hint=vi.parse_node_id(text))

"""
voice_agent.py -- Deepgram Voice Agent: TALK to Aegis while it routes.

This is the live control surface. The Deepgram Voice Agent API is a single
socket that chains Nova-3 STT -> an LLM that can call functions -> Aura-2 TTS.
The dispatcher just speaks:

    'Aegis, new emergency -- two people trapped at grid E5, critical.'

Nova-3 transcribes it, the LLM decides to call add_sar_location(grid='E5',
demand=2, priority='critical'), our handler drops a new node on the coordinate
grid in Redis and reroutes through the real solver, and Aura-2 speaks the new
plan back. Voice is the interface -- not a feature bolted on the side.

Two entry points, ONE tool dispatch:
  run_live(store)     -> real Deepgram Voice Agent socket (needs key + mic)
  handle_text(text)   -> same tools from typed input (offline demo + tests)
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, Optional

from . import grid

# ---- priority words -> the numeric priority the solver/contract expects ----
PRIORITY_WORDS = {
    "critical": 10.0, "life threatening": 10.0, "mayday": 10.0,
    "high": 8.0, "urgent": 8.0, "serious": 8.0,
    "medium": 5.0, "moderate": 5.0,
    "low": 2.0, "minor": 2.0, "stable": 2.0,
}


def _priority_value(p) -> float:
    if isinstance(p, (int, float)):
        return float(p)
    if not p:
        return 8.0
    return PRIORITY_WORDS.get(str(p).strip().lower(), 8.0)


def _count_victims(text: str) -> Optional[int]:
    t = text.lower()
    m = re.search(r"(\d+)\s*(?:people|persons?|victims?|trapped|casualt|injured|souls?)", t)
    if m:
        return int(m.group(1))
    for word, n in grid._WORD_NUM.items():
        if re.search(r"\b" + word + r"\b\s*(?:people|persons?|victims?|trapped|casualt|injured|souls?)", t):
            return n
    return None


def _priority_from_text(text: str) -> Optional[str]:
    t = text.lower()
    for word in PRIORITY_WORDS:
        if word in t:
            return word
    return None


class DispatcherCopilot:
    """The brain behind the voice: turns intents into Redis edits + reroutes.

    The SAME tool methods are invoked by the live Deepgram Voice Agent (via
    function-call events) and by the offline handle_text() path, so what you
    test offline is exactly what runs on stage.
    """

    def __init__(self, store, solver_fn: Optional[Callable] = None, tts=None,
                 api_key: Optional[str] = None, llm_model: Optional[str] = None):
        self.store = store
        self.solver_fn = solver_fn or self._default_solver()
        self.tts = tts
        self.api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
        self.llm_model = llm_model or os.environ.get("AEGIS_AGENT_LLM", "gpt-4o-mini")

    # ----------------------------------------------------------------- tools
    def add_sar_location(self, grid_ref: Optional[str] = None,
                         lat: Optional[float] = None, lng: Optional[float] = None,
                         demand: int = 1, priority="high",
                         label: Optional[str] = None, hazard: Optional[str] = None) -> dict:
        """Drop a NEW search-and-rescue node onto the coordinate grid and wire it
        into the road graph so the solver can reach it. O(1) live edit in Redis."""
        if grid_ref:
            lat, lng = grid.grid_to_latlng(grid_ref)
        if lat is None or lng is None:
            raise ValueError("add_sar_location needs grid_ref or lat/lng")
        square = grid_ref.upper() if grid_ref else grid.latlng_to_grid(lat, lng)

        new_id = max(self.store.all_node_ids()) + 1
        pri = _priority_value(priority)
        self.store.set_node(new_id, lat=lat, lng=lng, type="evacuee",
                            demand=int(demand), priority=pri,
                            tw_start=0, tw_end=600)

        # connect to the 3 nearest reachable nodes (skip the fire front)
        neighbors = grid.nearest_nodes(self.store, lat, lng, k=3)
        wired = []
        for nid, dist in neighbors:
            n = self.store.get_node(nid)
            cost = grid.edge_cost(lat, lng, float(n["lat"]), float(n["lng"]))
            self.store.set_base_edge(new_id, nid, cost)
            wired.append({"node": nid, "cost": cost})

        alias = label or f"grid {square}"
        self.store.set_node_alias(alias.lower(), new_id)
        if hazard:
            try:
                self.store.set_node_field(new_id, "hazard", hazard)
            except Exception:
                pass

        return {"ok": True, "node_id": new_id, "grid": square,
                "lat": lat, "lng": lng, "demand": int(demand),
                "priority": pri, "neighbors": wired, "alias": alias}

    def block_road(self, name: str, reason: str = "voice: road closed") -> dict:
        """Mark a road impassable -> huge multiplier (a negative weight)."""
        eid = self.store.resolve_alias(name.lower())
        if not eid:
            return {"ok": False, "error": f"unknown road: {name}"}
        i, j = eid
        self.store.set_edge_multiplier(i, j, 1000.0, reason=reason)
        return {"ok": True, "edge": [i, j], "road": name, "reason": reason}

    def reroute(self) -> dict:
        """Rebuild the contract from live Redis state and run the real solver.
        Writes the solution back + publishes aegis:routes:update for the map."""
        from contract_builder import build_contract
        from solver_bridge import run_solver
        build_contract(self.store)
        solution = run_solver(self.store, self.solver_fn)
        return solution

    def status(self, ref: str) -> dict:
        """Report a node's live status (accepts a grid square or an alias)."""
        nid = None
        sq = grid.find_grid_ref(ref)
        if sq is None:
            nid = self.store.resolve_node_alias(ref.lower())
        if nid is None and sq is not None:
            nid = self.store.resolve_node_alias(f"grid {sq}".lower())
        if nid is None:
            return {"ok": False, "error": f"unknown location: {ref}"}
        return {"ok": True, "node_id": nid, "node": self.store.get_node(nid)}

    # ------------------------------------------------- shared dispatch table
    def _dispatch(self, name: str, args: dict) -> dict:
        """Single source of truth: maps a function name -> tool. Used by BOTH
        the live Deepgram agent and the offline text path."""
        args = args or {}
        if name == "add_sar_location":
            res = self.add_sar_location(
                grid_ref=args.get("grid") or args.get("grid_ref"),
                lat=args.get("lat"), lng=args.get("lng") or args.get("lon"),
                demand=int(args.get("demand", 1) or 1),
                priority=args.get("priority", "high"),
                label=args.get("label"), hazard=args.get("hazard"))
            res["solution"] = self.reroute()
            return res
        if name == "block_road":
            res = self.block_road(args.get("name") or args.get("road", ""))
            if res.get("ok"):
                res["solution"] = self.reroute()
            return res
        if name in ("reroute", "optimize", "get_route"):
            return {"ok": True, "solution": self.reroute()}
        if name == "status":
            return self.status(args.get("location") or args.get("ref", ""))
        return {"ok": False, "error": f"unknown function: {name}"}

    # ------------------------------------------------ offline NLU (no mic/key)
    def handle_text(self, text: str, speak: bool = True) -> dict:
        """Run the FULL reroute-by-voice loop from a typed line. Same dispatch
        the live agent uses -- proves the loop offline and in tests."""
        t = text.lower()
        intent, args = "unknown", {}

        if any(k in t for k in ("emergency", "trapped", "casualt", "victim",
                                "rescue", "injured", "mayday", "new sar",
                                "new location", "add ")):
            intent, args = "add_sar_location", {
                "grid": grid.find_grid_ref(text),
                "demand": _count_victims(text) or 1,
                "priority": _priority_from_text(text) or "high",
            }
            mll = re.search(r"(-?\d{2}\.\d+)[,\s]+(-?\d{3}\.\d+)", text)
            if mll and not args["grid"]:
                args["lat"], args["lng"] = float(mll.group(1)), float(mll.group(2))
        elif any(k in t for k in ("block", "closed", "impassable", "bridge out",
                                  "fire on", "shut down", "can't use", "cannot use")):
            intent = "block_road"
            for alias in ("hwy 9", "route 3", "route 4", "coastal road",
                          "ridge pass", "river crossing", "canyon road", "main st"):
                if alias in t:
                    args = {"name": alias}
                    break
        elif any(k in t for k in ("status", "where is", "what's at", "whats at")):
            intent = "status"
            args = {"location": grid.find_grid_ref(text) or text}
        elif any(k in t for k in ("reroute", "re-route", "optimize", "best route", "plan")):
            intent = "reroute"

        result = self._dispatch(intent, args) if intent != "unknown" else {
            "ok": False, "error": "no intent recognised"}
        said = self.narrate(intent, args, result)
        if speak and self.tts is not None and result.get("ok", False):
            try:
                self.tts.speak(said, out_path=os.path.join("voice", "out", "advisory.wav"))
            except Exception:
                pass
        return {"intent": intent, "args": args, "said": said, "result": result}

    # --------------------------------------------------------- spoken replies
    def narrate(self, intent: str, args: dict, result: dict) -> str:
        if not result.get("ok", False):
            return f"Unable to comply: {result.get('error', 'unknown error')}."
        if intent == "add_sar_location":
            sol = result.get("solution", {})
            v = _victim_phrase(result.get("demand", 1))
            tail = _route_phrase(sol)
            return (f"Copy. New rescue site at grid {result['grid']}, node "
                    f"{result['node_id']}, priority {_pri_word(result['priority'])}, "
                    f"{v}. {tail}")
        if intent == "block_road":
            return (f"Acknowledged. {args.get('name', 'road').title()} marked "
                    f"impassable. {_route_phrase(result.get('solution', {}))}")
        if intent in ("reroute", "optimize", "get_route"):
            return "Recomputed. " + _route_phrase(result.get("solution", {}))
        if intent == "status":
            n = result.get("node", {})
            return (f"Node {result['node_id']}: type {n.get('type', '?')}, "
                    f"priority {n.get('priority', '?')}, demand {n.get('demand', '?')}.")
        return "Done."

    # --------------------------------------------- Deepgram Voice Agent config
    def agent_settings(self) -> dict:
        """The Deepgram Voice Agent 'Settings' payload: STT + LLM(+functions) + TTS
        in one socket. This is what makes the agent able to ACT on speech."""
        functions = [
            {"name": "add_sar_location",
             "description": "Add a new search-and-rescue / casualty site to the "
                            "map and reroute vehicles to it.",
             "parameters": {"type": "object", "properties": {
                 "grid": {"type": "string",
                          "description": "Grid square like 'E5' or phonetic 'echo five'."},
                 "demand": {"type": "integer", "description": "Number of victims."},
                 "priority": {"type": "string",
                              "enum": ["critical", "high", "medium", "low"]},
                 "hazard": {"type": "string", "description": "Optional hazard note."}},
                 "required": ["grid"]}},
            {"name": "block_road",
             "description": "Mark a named road impassable (fire, collapse) and reroute.",
             "parameters": {"type": "object", "properties": {
                 "name": {"type": "string",
                          "description": "Road name, e.g. 'Hwy 9', 'coastal road'."}},
                 "required": ["name"]}},
            {"name": "reroute",
             "description": "Recompute optimal routes from current live state.",
             "parameters": {"type": "object", "properties": {}}},
            {"name": "status",
             "description": "Report the live status of a grid square or location.",
             "parameters": {"type": "object", "properties": {
                 "location": {"type": "string"}}, "required": ["location"]}},
        ]
        return {
            "type": "Settings",
            "audio": {
                "input": {"encoding": "linear16", "sample_rate": 16000},
                "output": {"encoding": "linear16", "sample_rate": 24000,
                           "container": "none"},
            },
            "agent": {
                "language": "en",
                "listen": {"provider": {"type": "deepgram", "model": "nova-3",
                                        "keyterms": grid._COLS and None or None}},
                "think": {
                    "provider": {"type": "open_ai", "model": self.llm_model},
                    "prompt": ("You are Aegis, a wildfire search-and-rescue dispatch "
                               "copilot. Dispatchers speak terse radio traffic. When they "
                               "report a new emergency, call add_sar_location with the grid "
                               "square, victim count and priority, then confirm the new "
                               "route in one short sentence. When they report a road "
                               "closed, call block_road. Keep replies under 2 sentences, "
                               "use NATO phonetics for grid squares, and always state the "
                               "updated route or ETA."),
                    "functions": functions,
                },
                "speak": {"provider": {"type": "deepgram", "model": "aura-2-thalia-en"}},
                "greeting": "Aegis online. Routing active. Report when ready.",
            },
        }

    def _default_solver(self):
        """Prefer the real OR-Tools solver via the adapter; fall back to the
        bundled mock so reroute always returns a plan, even offline."""
        try:
            from solver.adapters.aegis_contract import solve_contract  # type: ignore
            return solve_contract
        except Exception:
            try:
                from solver_bridge import mock_solver
                return mock_solver
            except Exception:
                return None

    # ------------------------------------------------------- live voice agent
    def run_live(self, on_event: Optional[Callable] = None):
        """Open the real Deepgram Voice Agent socket: mic in -> agent -> speaker
        out, with our functions wired so speech can actually edit the map and
        reroute. Needs DEEPGRAM_API_KEY + a microphone. No-ops gracefully if the
        environment can't support it (prints how to enable)."""
        if not self.api_key:
            print("[voice_agent] set DEEPGRAM_API_KEY to run the live Voice Agent.")
            print("[voice_agent] meanwhile, use handle_text('new emergency at E5...').")
            return
        try:
            from deepgram import DeepgramClient
            from deepgram.clients.agent.v1.websocket.options import SettingsOptions  # noqa
        except Exception as e:
            print(f"[voice_agent] deepgram agent SDK unavailable ({e}). "
                  "pip install 'deepgram-sdk>=3.7' and a mic backend (pyaudio).")
            return

        client = DeepgramClient(self.api_key)
        try:
            conn = client.agent.websocket.v("1")
        except Exception as e:
            print(f"[voice_agent] could not open agent socket ({e}).")
            return

        from deepgram.clients.agent.v1.websocket.events import AgentWebSocketEvents

        def _on_function_call(_, payload, **kw):
            # payload carries function name, arguments and a call id
            try:
                data = payload if isinstance(payload, dict) else json.loads(str(payload))
            except Exception:
                data = {}
            name = data.get("function_name") or data.get("name")
            args = data.get("input") or data.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            result = self._dispatch(name, args)
            if on_event:
                on_event("function_call", {"name": name, "args": args, "result": result})
            try:
                conn.send_function_call_response(
                    function_call_id=data.get("function_call_id") or data.get("id"),
                    output=json.dumps(_compact_solution(result)))
            except Exception as e:
                print(f"[voice_agent] failed to return function result ({e}).")

        def _on_text(_, payload, **kw):
            if on_event:
                on_event("conversation", payload)

        try:
            conn.on(AgentWebSocketEvents.FunctionCallRequest, _on_function_call)
            conn.on(AgentWebSocketEvents.ConversationText, _on_text)
        except Exception:
            pass

        print("[voice_agent] starting live Deepgram Voice Agent. Speak your dispatch.")
        print("[voice_agent] try: 'New emergency, two trapped at grid echo five, critical.'")
        try:
            conn.start(self.agent_settings())
            from deepgram.audio import Microphone  # type: ignore
            mic = Microphone(conn.send)
            mic.start()
            input("Press Enter to end the session...\n")
            mic.finish()
            conn.finish()
        except Exception as e:
            print(f"[voice_agent] live session ended ({e}).")


# ---- narration helpers -----------------------------------------------------
def _pri_word(p) -> str:
    p = float(p)
    if p >= 9:
        return "critical"
    if p >= 7:
        return "high"
    if p >= 4:
        return "medium"
    return "low"


def _victim_phrase(n) -> str:
    n = int(n)
    return "one victim" if n == 1 else f"{n} victims"


def _route_phrase(sol: dict) -> str:
    if not sol:
        return "No route available."
    veh = sol.get("vehicles") or sol.get("routes") or []
    n = len([v for v in veh if (v.get("route") or v.get("stops"))]) or len(veh)
    cost = sol.get("total_cost", sol.get("cost"))
    dropped = sol.get("dropped", [])
    parts = [f"Rerouting {n} unit{'s' if n != 1 else ''}"]
    if cost is not None:
        parts.append(f"total cost {round(float(cost), 1)}")
    if dropped:
        parts.append(f"{len(dropped)} site(s) deferred")
    return ", ".join(parts) + "."


def _compact_solution(result: dict) -> dict:
    """Trim a solver solution to what the agent needs to speak (token thrift)."""
    out = {k: v for k, v in result.items() if k != "solution"}
    sol = result.get("solution")
    if isinstance(sol, dict):
        out["route"] = {"total_cost": sol.get("total_cost", sol.get("cost")),
                        "units": len(sol.get("vehicles", sol.get("routes", []))),
                        "dropped": sol.get("dropped", [])}
    return out
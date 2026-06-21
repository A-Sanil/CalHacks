# 🛰️ Project Aegis Route
### Real-time agentic optimization for wildfire search & rescue — **voice-first**, grounded in the January 2025 Palisades Fire.

![tests](https://img.shields.io/badge/tests-46%20passing-brightgreen) ![python](https://img.shields.io/badge/python-3.11-blue) ![Deepgram](https://img.shields.io/badge/Deepgram-Nova--3%20%7C%20Aura--2%20%7C%20Voice%20Agent-7C3AED) ![OR-Tools](https://img.shields.io/badge/solver-OR--Tools%20CVRP-orange) ![Redis](https://img.shields.io/badge/state-Redis%20O(1)-red) ![React](https://img.shields.io/badge/dashboard-React%20%2B%20SVG-06B6D4)

> **Turn the chaos of disaster comms into an O(1) live state — then reroute the instant someone speaks.**

Wildfire search-and-rescue runs on *voice*: 911 calls, dispatch radio, field units on the net. Aegis listens to that traffic, extracts what changed (a bridge is out, six trapped at the high school), writes it to a live graph in **O(1)**, and re-optimizes multi-vehicle rescue routes — continuously. Then it **speaks the new plan back** to the crews.

---

## 🎤 Voice is the front door — powered by Deepgram

Voice isn't bolted on; it's the **primary I/O of the whole system**. Without speech-to-text there is no data to optimize on. Aegis uses Deepgram across four load-bearing surfaces:

| Deepgram product | Where it lives in Aegis | Why it's essential |
|---|---|---|
| **STT — Nova-3** | The front door: 911 calls + dispatch radio → `ingest.Signal` → negative edge weights | No transcript = no live state = nothing to solve |
| **STT streaming** | Live radio-scanner feed → graph updates as the call is still happening | Reroutes mid-incident |
| **TTS — Aura-2** | The solver's route → spoken advisory to field units | Hands-free instructions in a moving truck; closes the loop |
| **Voice Agent API** | *Talk* to Aegis: "new emergency at grid E5" → it acts + replies | Voice as the control surface — the marquee demo |

**SAR-tuned, not a vanilla call:** keyterm prompting (street names + survival vocab survive radio noise), speaker **diarization** (caller vs dispatcher), `smart_format`/`numerals` for addresses & unit numbers, and PII **redaction** for real 911 audio.

### ⭐ The marquee moment — reroute by voice, on a coordinate grid

Mid-mission, the dispatcher just talks. The **Deepgram Voice Agent** (one socket: Nova-3 → an LLM with function-calling → Aura-2) decides to call an Aegis tool:

> **Dispatcher (out loud):** "Aegis, new emergency — two people trapped at grid **echo five**, critical."  
> **→** agent calls `add_sar_location(grid="E5", demand=2, priority="critical")`  
> **→** a new node drops onto the coordinate grid in Redis, wired to its nearest roads  
> **→** the **real OR-Tools solver** re-optimizes over live edge costs  
> **Aegis (spoken back):** "Copy. New rescue site at grid E5, node 10, priority critical, two victims. Rerouting 2 units, total cost 43."

```text
  🎙️  speech ──Nova-3──▶ intent + args ──▶ add_sar_location / block_road / reroute
                                              │
                                  O(1) edit ▼ (new node + edges on the grid)
                                           Redis live state
                                              │  build_contract → run_solver (OR-Tools)
                                              ▼
                            new routes ──Aura-2──▶ 🔊 spoken advisory + 🗺️ dashboard
```

Grid squares use NATO phonetics too — "echo five", "E-5", and `E5` all resolve to the same lat/lng inside the Palisades operating box.

---

## 🏗️ Architecture

```text
  AUDIO                      BRAIN                    STATE (O(1))         SOLVE              VOICE OUT
  911 call ─┐                                                                                          
  radio ────┼─▶ Deepgram ─▶ Extractor Agent ─▶  Redis live layer  ─▶ build_contract ─▶  Aura-2 TTS 🔊
  field ────┘    STT          (+ semantic        base × multiplier      run_solver        + pub/sub 🗺️
                              cache)             node priorities       (OR-Tools CVRP)
                                                      ▲
                                       GraphRAG static knowledge graph
                                       (roads, terrain — indexed once)
```

Two layers, decoupled on purpose:
- **GraphRAG = static** knowledge graph (roads, terrain) — pre-indexed once.
- **Redis = live** state — real-time edge weights & node priorities, O(1) updates, independent of when you solve.

---

## ⚡ Quickstart

```bash
python -m venv .venv && .venv\Scripts\activate    # (Windows)  |  source .venv/bin/activate
pip install -r requirements.txt

pytest -q                 # 46 tests, fully offline (fakeredis, no API keys needed)
python voice_demo.py      # the Deepgram story: 911 calls → reroutes → spoken advisories
```

Everything runs **offline by default** — `fakeredis`, sidecar transcripts, and a graceful solver fallback — so the demo always works on stage. Add a Deepgram key to go live (below).

---

## 🗂️ The voice layer

| Module | Role |
|---|---|
| `voice/deepgram_stt.py` | **Ears.** Audio → transcript → `ingest.Signal` (batch + live streaming, SAR keyterms, diarize, redact) |
| `voice/deepgram_tts.py` | **Mouth.** Advisory text → spoken Aura-2 audio for field units |
| `voice/voice_agent.py` | **Brain + voice.** Deepgram Voice Agent with function-calling tools: `add_sar_location`, `block_road`, `reroute`, `status` |
| `voice/grid.py` | Coordinate grid ↔ lat/lng (A–H × 1–8), NATO phonetics, nearest-node wiring |
| `voice/dispatch_pipeline.py` | The full loop: `process_call(audio)` → STT → extractor → Redis → solver → TTS |
| `voice/samples/` | Realistic 911/dispatch transcripts (hit real graph roads & nodes) |

The same tool dispatch backs both the **live** Voice Agent (`run_live()`) and the **offline** path (`handle_text()`) — so what you test offline is exactly what runs live.

---

## 🧪 Tests & metrics

- **46 tests passing** (38 system + 8 new voice) — `pytest -q`, no keys required.
- **Stress:** 12,000 ticks → 480 solves, **96% semantic-cache hit**, **4.84M tokens saved**, all invariants held.
- Voice-triggered reroute calls the **real OR-Tools CVRP** solver with a Dijkstra live-cost matrix — a blocked road or a new node reroutes via true shortest path.

---

## 🔑 Going live with Deepgram

```bash
export DEEPGRAM_API_KEY=dg_xxx          # unlocks Nova-3 STT, Aura-2 TTS, Voice Agent
python voice/make_sample_audio.py       # synth the sample calls to real .wav (Aura-2)
python voice_demo.py                     # now transcribes REAL audio with Nova-3
python voice_demo.py --live              # talk to Aegis: live Voice Agent (needs a mic)
```

Optional env: `DEEPGRAM_STT_MODEL` (default `nova-3`), `DEEPGRAM_TTS_MODEL` (default `aura-2-thalia-en`), `AEGIS_AGENT_LLM` (Voice Agent think model).

---

## 📚 More docs

- [COMPLETE.md](COMPLETE.md) — full system walkthrough & PDF→code mapping
- [INTEGRATION.md](INTEGRATION.md) — solver ↔ frontend wiring
- [DEMO.md](DEMO.md) — live demo script
- [SLIDES.md](SLIDES.md) — presentation deck (also rendered: `Project-Aegis-Route.pptx`)

---

<sub>Built for CalHacks. GraphRAG + Redis + LLM agent + OR-Tools + React — with **Deepgram** as the voice that drives it all.</sub>

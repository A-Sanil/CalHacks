"""
voice_demo.py -- the Deepgram story, end to end, in your terminal.

  python voice_demo.py            # scripted: 911 calls -> reroutes -> advisories
  python voice_demo.py --live     # real Deepgram Voice Agent (needs key + mic)

Offline it runs entirely on the .txt sample sidecars + mock/real solver, so it
always works on stage. With DEEPGRAM_API_KEY set it uses Nova-3 + Aura-2 for real.
"""
import os
import sys

from redis_store import AegisStore
from graph_seed import seed_demo
from voice.dispatch_pipeline import DispatchPipeline
from voice.voice_agent import DispatcherCopilot


def banner(t):
    print("\n" + "=" * 68 + "\n  " + t + "\n" + "=" * 68)


def scripted():
    store = AegisStore()
    seed_demo(store)
    pipe = DispatchPipeline(store)

    banner("ACT 1  --  Incoming 911 + dispatch radio (Deepgram STT -> Redis)")
    for clip in ("911_hwy9_bridge", "911_highschool_trapped", "911_canyon_road_fire"):
        path = os.path.join("voice", "samples", clip + ".txt")
        out = pipe.process_call(path, reroute=False, speak=False)
        print(f"\n[{out['stt_source'].upper()}/{out['stt_model']}] {clip}")
        print("  transcript:", out["transcript"][:90], "...")
        print("  -> updates:", out["updates"])

    banner("ACT 2  --  Solve on the live state (real OR-Tools)")
    sol = DispatcherCopilot(store).reroute()
    print("  total_cost:", sol.get("total_cost"),
          "| units:", len(sol.get("vehicles", [])),
          "| dropped:", sol.get("dropped"))

    banner("ACT 3  --  Voice Agent: NEW emergency mid-mission, by coordinate grid")
    cop = DispatcherCopilot(store)
    for spoken in (
        "Aegis, new emergency -- two people trapped at grid echo five, critical.",
        "Be advised, block coastal road, it's impassable.",
    ):
        print(f"\n  DISPATCHER (spoken): {spoken}")
        r = cop.handle_text(spoken, speak=False)
        print(f"  AEGIS (spoken back): {r['said']}")

    banner("DONE  --  voice in, reroute, voice out. Set DEEPGRAM_API_KEY to go live.")


def live():
    store = AegisStore()
    seed_demo(store)
    DispatcherCopilot(store).run_live(
        on_event=lambda kind, p: print(f"[{kind}] {p}"))


if __name__ == "__main__":
    (live if "--live" in sys.argv else scripted)()
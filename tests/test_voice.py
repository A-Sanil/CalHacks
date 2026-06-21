"""
test_voice.py -- the Deepgram voice layer, fully offline (no key / no mic).
Proves: STT fallback, audio->negative-weights, TTS, and the marquee feature --
speak a new emergency by grid square and watch the solver reroute to it.
"""
import os
import pytest

from redis_store import AegisStore
from graph_seed import seed_demo
from voice import grid
from voice.deepgram_stt import DeepgramSTT, to_signal
from voice.deepgram_tts import DeepgramTTS
from voice.voice_agent import DispatcherCopilot
from voice.dispatch_pipeline import DispatchPipeline

SAMPLES = os.path.join("voice", "samples")


@pytest.fixture
def store():
    s = AegisStore()
    seed_demo(s)
    return s


# ---- grid -----------------------------------------------------------------
def test_grid_roundtrip():
    lat, lng = grid.grid_to_latlng("E5")
    assert grid.LAT_MIN <= lat <= grid.LAT_MAX
    assert grid.LNG_MIN <= lng <= grid.LNG_MAX
    assert grid.latlng_to_grid(lat, lng) == "E5"


def test_grid_speech_parsing():
    assert grid.find_grid_ref("trapped at grid echo five, critical") == "E5"
    assert grid.find_grid_ref("victims at E-5 now") == "E5"
    assert grid.find_grid_ref("no coordinates here") is None


# ---- STT ------------------------------------------------------------------
def test_stt_fallback_reads_sidecar():
    stt = DeepgramSTT(api_key=None)
    res = stt.transcribe_file(os.path.join(SAMPLES, "911_hwy9_bridge.txt"))
    assert res.source == "fallback"
    assert "hwy 9" in res.text.lower()


def test_to_signal_shape():
    stt = DeepgramSTT(api_key=None)
    res = stt.transcribe_file(os.path.join(SAMPLES, "911_canyon_road_fire.txt"))
    sig = to_signal(res, source="phone_call", channel="911")
    assert sig.text and sig.meta["transcribed"] is True


# ---- audio -> negative weights -------------------------------------------
def test_pipeline_applies_negative_weight(store):
    pipe = DispatchPipeline(store)
    out = pipe.process_call(os.path.join(SAMPLES, "911_hwy9_bridge.txt"),
                            reroute=False, speak=False)
    assert out["updates"], "extractor should produce updates from the call"
    # the call reports a road closure -> at least one edge gets a negative weight
    # (final cost pushed above its base cost via a live multiplier)
    elevated = [(i, j) for (i, j) in store.all_edges()
                if store.get_final_cost(i, j) > float(store.get_edge(i, j)["base_cost"])]
    assert elevated, "a road-closure call must raise some edge's cost (negative weight)"


# ---- TTS ------------------------------------------------------------------
def test_tts_fallback_writes_text(tmp_path):
    tts = DeepgramTTS(api_key=None)
    out = tts.speak("Engine 12 reroute via coastal road.",
                    out_path=str(tmp_path / "advisory.wav"))
    assert out.endswith(".txt") and os.path.exists(out)


# ---- THE marquee feature: voice adds a SAR node + reroutes ----------------
def test_voice_adds_sar_location_and_reroutes(store):
    cop = DispatcherCopilot(store)
    before = set(store.all_node_ids())
    r = cop.handle_text(
        "Aegis, new emergency, two people trapped at grid echo five, critical.",
        speak=False)
    after = set(store.all_node_ids())

    assert r["intent"] == "add_sar_location"
    assert len(after) == len(before) + 1, "a new node must appear on the grid"
    new_id = max(after)
    node = store.get_node(new_id)
    assert node["type"] == "evacuee"
    assert int(node["demand"]) == 2
    assert float(node["priority"]) >= 9        # 'critical'
    # the new node was wired into the graph (has at least one edge)
    assert any(new_id in (i, j) for (i, j) in store.all_edges())
    # and the solver actually produced a fresh plan
    assert r["result"]["solution"] is not None
    assert "grid E5" in r["said"]


def test_voice_block_road_then_reroute(store):
    cop = DispatcherCopilot(store)
    r = cop.handle_text("Be advised, block canyon road, it's impassable.", speak=False)
    assert r["intent"] == "block_road"
    assert r["result"]["ok"] is True
    # canyon road == edge (6,8); now penalised
    assert store.get_final_cost(6, 8) > float(store.get_edge(6, 8)["base_cost"])
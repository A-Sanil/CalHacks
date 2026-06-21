"""
dispatch_pipeline.py -- the whole loop, end to end.

   audio (911 call / scanner clip)
       |  Deepgram STT (nova-3, keyterms, diarize, redact)
       v
   transcript --> ingest.Signal
       |  ExtractorAgent (unstructured -> structured) + SemanticCache
       v
   Redis live state (negative weights, node priorities)   [O(1)]
       |  build_contract -> run_solver (real OR-Tools)
       v
   solution  --> Deepgram TTS (aura-2) spoken advisory  --> field units
                 + publish aegis:routes:update           --> dashboard

One call -- process_call(audio_path) -- runs the entire chain and returns a
structured trace you can print, assert on, or render on the map.
"""
from __future__ import annotations

import os
from typing import Optional

from .deepgram_stt import DeepgramSTT, to_signal
from .deepgram_tts import DeepgramTTS
from .voice_agent import DispatcherCopilot, _route_phrase


class DispatchPipeline:
    def __init__(self, store, stt: Optional[DeepgramSTT] = None,
                 tts: Optional[DeepgramTTS] = None, solver_fn=None):
        self.store = store
        self.stt = stt or DeepgramSTT()
        self.tts = tts or DeepgramTTS()
        self.copilot = DispatcherCopilot(store, solver_fn=solver_fn, tts=self.tts)
        from extractor_agent import ExtractorAgent
        self.extractor = ExtractorAgent(store)

    def process_call(self, audio_path: str, channel: str = "911",
                     source: str = "phone_call", reroute: bool = True,
                     speak: bool = True) -> dict:
        """Transcribe one clip, fold it into live state, reroute, and (optionally)
        speak the advisory. Returns the full trace."""
        # 1) ears: audio -> transcript
        result = self.stt.transcribe_file(audio_path)
        sig = to_signal(result, source=source, channel=channel)

        # 2) brain: transcript -> structured Redis updates (negative weights etc.)
        extracted = self.extractor.process(sig)
        updates = extracted.get("updates", [])

        # 3) reroute on the new live state via the real solver
        solution = self.copilot.reroute() if reroute else None

        # 4) mouth: speak the advisory back to the field
        advisory = self._advisory(result, updates, solution)
        spoken_path = None
        if speak:
            os.makedirs(os.path.join("voice", "out"), exist_ok=True)
            spoken_path = self.tts.speak(
                advisory, out_path=os.path.join("voice", "out", "advisory.wav"))

        return {
            "audio": audio_path,
            "transcript": result.text,
            "stt_source": result.source,         # 'deepgram' live, else 'fallback'
            "stt_model": result.model,
            "updates": updates,
            "thought": extracted.get("thought"),
            "cached": extracted.get("cached"),
            "solution": solution,
            "advisory": advisory,
            "advisory_audio": spoken_path,
        }

    def speak_dispatch(self, text: str, speak: bool = True) -> dict:
        """Spoken/typed dispatcher command (the live Voice Agent equivalent):
        'New emergency, two trapped at grid E5, critical.'"""
        return self.copilot.handle_text(text, speak=speak)

    def _advisory(self, result, updates, solution) -> str:
        bits = []
        if updates:
            tgt = updates[0].get("target", "state")
            bits.append(f"{len(updates)} live update(s) applied to {tgt}")
        else:
            bits.append("Logged, no map change")
        if solution:
            bits.append(_route_phrase(solution))
        return ". ".join(bits)

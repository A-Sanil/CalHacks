"""
deepgram_stt.py -- Deepgram Speech-to-Text: the FRONT DOOR of Aegis.

911 calls and dispatch radio are *audio*. This module turns that audio into the
text Signals the extractor already understands -- so the whole optimizer runs on
real spoken emergency traffic instead of hand-typed strings.

Modes
-----
transcribe_file(path)       batch : a recorded 911 call / archived scanner clip
transcribe_stream(chunks)   live  : a real-time radio-scanner feed (interim results)

SAR tuning (why this beats a vanilla STT call)
----------------------------------------------
* keyterm prompting    -> boosts street names + survival vocab ('evac', 'trapped',
                          'Hwy 9', 'Palisades') so addresses survive radio noise
* diarize              -> separates caller vs dispatcher vs field unit
* smart_format/numerals-> clean addresses, unit numbers, mile markers
* redact               -> strips PII (phone/SSN) from real 911 audio (ethics + legal)

Graceful degradation
--------------------
No DEEPGRAM_API_KEY or no deepgram-sdk -> fall back to a sidecar '<clip>.txt'
transcript so the demo runs fully offline. Set DEEPGRAM_API_KEY to go live.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional

# Street + place names from the seeded Palisades graph (graph_seed aliases) plus
# survival vocabulary. Handed to Deepgram as keyterms so it locks onto them even
# over a noisy radio channel.
SAR_KEYTERMS: List[str] = [
    # roads / edges
    "Hwy 9", "Route 3", "Route 4", "coastal road", "ridge pass",
    "river crossing", "canyon road", "Main Street", "Sunset Boulevard",
    "Palisades Drive", "Pacific Coast Highway",
    # places / nodes
    "high school", "evac point", "north shelter", "ridge camp",
    "south camp", "general hospital", "clinic", "fire station",
    # survival vocabulary
    "evacuate", "trapped", "casualty", "injured", "structure fire",
    "spot fire", "ember", "downed power line", "road closed", "bridge out",
    "mandatory evacuation", "shelter in place", "non-ambulatory",
]

DEFAULT_MODEL = os.environ.get("DEEPGRAM_STT_MODEL", "nova-3")


@dataclass
class TranscriptResult:
    """Normalised transcription result -- identical shape live or offline."""
    text: str
    source: str = "fallback"          # "deepgram" | "fallback"
    confidence: float = 1.0
    words: int = 0
    speakers: int = 0
    model: str = DEFAULT_MODEL
    raw: Optional[dict] = field(default=None, repr=False)

    @property
    def is_live(self) -> bool:
        return self.source == "deepgram"


class DeepgramSTT:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL,
                 keyterms: Optional[List[str]] = None):
        self.api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
        self.model = model
        self.keyterms = keyterms or SAR_KEYTERMS
        self._client = self._make_client()

    def _make_client(self):
        if not self.api_key:
            return None
        try:
            from deepgram import DeepgramClient
            return DeepgramClient(self.api_key)
        except Exception as e:  # SDK missing / bad key -> stay offline
            print(f"[deepgram_stt] SDK unavailable ({e}); using offline fallback.")
            return None

    @property
    def live(self) -> bool:
        return self._client is not None

    # ---- batch -------------------------------------------------------------
    def transcribe_file(self, path: str) -> TranscriptResult:
        # .txt inputs are treated as already-transcribed clips
        if path.lower().endswith(".txt") and os.path.exists(path):
            return self._from_sidecar(path)

        if self.live and os.path.exists(path):
            try:
                return self._deepgram_file(path)
            except Exception as e:
                print(f"[deepgram_stt] live transcription failed ({e}); falling back.")

        # fallback: sidecar <base>.txt sitting next to the audio clip
        sidecar = os.path.splitext(path)[0] + ".txt"
        if os.path.exists(sidecar):
            return self._from_sidecar(sidecar)
        return TranscriptResult(text="", source="fallback", confidence=0.0, model="none")

    def _from_sidecar(self, path: str) -> TranscriptResult:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read().strip()
        return TranscriptResult(text=txt, source="fallback",
                                words=len(txt.split()), model="sidecar")

    def _deepgram_file(self, path: str) -> TranscriptResult:
        from deepgram import PrerecordedOptions, FileSource
        with open(path, "rb") as f:
            buf = f.read()
        options = PrerecordedOptions(
            model=self.model, smart_format=True, punctuate=True,
            numerals=True, diarize=True, language="en-US",
            keyterm=self.keyterms, redact=["pci", "ssn"],
        )
        payload: FileSource = {"buffer": buf}
        resp = self._client.listen.rest.v("1").transcribe_file(payload, options)
        alt = resp.results.channels[0].alternatives[0]
        words = alt.words or []
        speakers = len({getattr(w, "speaker", None) for w in words
                        if getattr(w, "speaker", None) is not None})
        return TranscriptResult(
            text=alt.transcript, source="deepgram",
            confidence=float(getattr(alt, "confidence", 1.0) or 1.0),
            words=len(words), speakers=speakers, model=self.model,
        )

    # ---- streaming (live radio scanner) -----------------------------------
    def transcribe_stream(self, chunks: Iterable[bytes],
                          on_partial: Optional[Callable[[str], None]] = None) -> TranscriptResult:
        """Live transcription of a radio-scanner byte stream (Broadcastify/SDR).
        Offline returns '' -- feed audio bytes to go live."""
        if not self.live:
            print("[deepgram_stt] no API key; live streaming disabled offline.")
            return TranscriptResult(text="", source="fallback", model="none")
        try:
            from deepgram import LiveOptions, LiveTranscriptionEvents
            finals: List[str] = []
            conn = self._client.listen.websocket.v("1")

            def _on_msg(_, result, **kw):
                sentence = result.channel.alternatives[0].transcript
                if not sentence:
                    return
                if result.is_final:
                    finals.append(sentence)
                elif on_partial:
                    on_partial(sentence)

            conn.on(LiveTranscriptionEvents.Transcript, _on_msg)
            conn.start(LiveOptions(model=self.model, language="en-US",
                                   smart_format=True, interim_results=True,
                                   keyterm=self.keyterms))
            for c in chunks:
                conn.send(c)
            conn.finish()
            return TranscriptResult(text=" ".join(finals), source="deepgram", model=self.model)
        except Exception as e:
            print(f"[deepgram_stt] streaming failed ({e}).")
            return TranscriptResult(text="", source="fallback", model="none")


# ---- module-level conveniences --------------------------------------------
_default: Optional[DeepgramSTT] = None


def transcribe_file(path: str) -> TranscriptResult:
    global _default
    if _default is None:
        _default = DeepgramSTT()
    return _default.transcribe_file(path)


def to_signal(result: TranscriptResult, source: str = "phone_call",
              channel: str = "911"):
    """Adapt a Deepgram transcript into the ingest.Signal the extractor eats.
    The rest of Aegis never learns the data came from audio."""
    from ingest import Signal
    return Signal(source=source, channel=channel, text=result.text,
                  meta={"stt": result.source, "model": result.model,
                        "confidence": result.confidence,
                        "speakers": result.speakers, "transcribed": True})

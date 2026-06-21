"""
deepgram_tts.py -- Deepgram Aura-2 Text-to-Speech: the MOUTH of Aegis.

After the solver produces routes, Aegis speaks the advisory back to field units:
    'Engine 12, Hwy 9 bridge is impassable -- reroute via coastal road to the
     high school evac point. Six casualties, priority critical.'
Voice OUT means crews get instructions hands-free in a moving truck.

Graceful: no DEEPGRAM_API_KEY / no deepgram-sdk -> writes the advisory text to a
'<out>.txt' file and returns that path, so the pipeline still completes offline.
"""
from __future__ import annotations

import os
from typing import Optional

DEFAULT_VOICE = os.environ.get("DEEPGRAM_TTS_MODEL", "aura-2-thalia-en")


class DeepgramTTS:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_VOICE):
        self.api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
        self.model = model
        self._client = self._make_client()

    def _make_client(self):
        if not self.api_key:
            return None
        try:
            from deepgram import DeepgramClient
            return DeepgramClient(self.api_key)
        except Exception as e:
            print(f"[deepgram_tts] SDK unavailable ({e}); using offline fallback.")
            return None

    @property
    def live(self) -> bool:
        return self._client is not None

    def speak(self, text: str, out_path: str = "advisory.wav") -> str:
        """Synthesize text to speech, return the written file path.
        Live -> a real .wav/.mp3; offline -> a .txt with the advisory."""
        if self.live:
            try:
                from deepgram import SpeakOptions
                options = SpeakOptions(model=self.model)
                self._client.speak.rest.v("1").save(out_path, {"text": text}, options)
                return out_path
            except Exception as e:
                print(f"[deepgram_tts] synthesis failed ({e}); writing text instead.")
        # offline fallback
        txt_path = os.path.splitext(out_path)[0] + ".txt"
        os.makedirs(os.path.dirname(txt_path) or ".", exist_ok=True)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        return txt_path


_default: Optional[DeepgramTTS] = None


def speak(text: str, out_path: str = "advisory.wav") -> str:
    global _default
    if _default is None:
        _default = DeepgramTTS()
    return _default.speak(text, out_path)

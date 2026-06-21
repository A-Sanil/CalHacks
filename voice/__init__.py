"""
Aegis voice layer -- Deepgram-powered ears, mouth, and conversational copilot.

Deepgram is the FRONT DOOR of Aegis. 911 calls and dispatch radio are *audio*;
this package turns that audio into the structured live state the optimizer runs
on -- then speaks routing advisories back to the field.

  deepgram_stt       audio  -> transcript -> ingest.Signal      (ears)
  deepgram_tts       advisory text -> spoken audio              (mouth)
  voice_agent        conversational dispatcher copilot          (brain+voice)
  dispatch_pipeline  audio -> STT -> extractor -> Redis -> solver -> TTS (the loop)

Importing this package auto-loads a local .env (if present) so DEEPGRAM_API_KEY
is available everywhere. With no key it all still runs offline (sidecar
transcripts + text advisories), like fakeredis / optional-torch elsewhere.
"""
import os as _os


def _load_dotenv():
    """Tiny, dependency-free .env loader. Walks up from CWD and this file's
    directory, setting any keys not already in the environment."""
    seen = []
    here = _os.path.dirname(__file__)
    for base in (_os.getcwd(), here, _os.path.dirname(here)):
        path = _os.path.join(base, ".env")
        if path in seen or not _os.path.exists(path):
            continue
        seen.append(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in _os.environ:
                        _os.environ[k] = v
        except OSError:
            pass


_load_dotenv()

from .deepgram_stt import DeepgramSTT, TranscriptResult, transcribe_file, to_signal, SAR_KEYTERMS
from .deepgram_tts import DeepgramTTS, speak
from .voice_agent import DispatcherCopilot
from .dispatch_pipeline import DispatchPipeline

__all__ = [
    "DeepgramSTT", "TranscriptResult", "transcribe_file", "to_signal", "SAR_KEYTERMS",
    "DeepgramTTS", "speak", "DispatcherCopilot", "DispatchPipeline",
]

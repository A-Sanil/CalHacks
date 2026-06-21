"""
Aegis voice layer -- Deepgram-powered ears, mouth, and conversational copilot.

Deepgram is the FRONT DOOR of Aegis. 911 calls and dispatch radio are *audio*;
this package turns that audio into the structured live state the optimizer runs
on -- then speaks routing advisories back to the field.

  deepgram_stt       audio  -> transcript -> ingest.Signal      (ears)
  deepgram_tts       advisory text -> spoken audio              (mouth)
  voice_agent        conversational dispatcher copilot          (brain+voice)
  dispatch_pipeline  audio -> STT -> extractor -> Redis -> solver -> TTS (the loop)

Everything degrades gracefully: with no DEEPGRAM_API_KEY the package runs fully
offline (sidecar transcripts + text advisories), exactly like fakeredis /
optional-torch elsewhere in Aegis. Set the key to go live.
"""
from .deepgram_stt import DeepgramSTT, TranscriptResult, transcribe_file, to_signal, SAR_KEYTERMS
from .deepgram_tts import DeepgramTTS, speak
from .voice_agent import DispatcherCopilot
from .dispatch_pipeline import DispatchPipeline

__all__ = [
    "DeepgramSTT", "TranscriptResult", "transcribe_file", "to_signal", "SAR_KEYTERMS",
    "DeepgramTTS", "speak", "DispatcherCopilot", "DispatchPipeline",
]

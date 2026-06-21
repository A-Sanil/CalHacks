"""
make_sample_audio.py -- turn the sample transcripts into real .wav clips using
Deepgram Aura-2 (needs DEEPGRAM_API_KEY). Lets the demo run on ACTUAL audio that
is then transcribed back by Nova-3 -- a full voice round trip. Offline this just
notes that the .txt sidecars are used directly.
"""
import glob, os
from voice.deepgram_tts import DeepgramTTS

def main():
    tts = DeepgramTTS()
    if not tts.live:
        print("No DEEPGRAM_API_KEY -> demo uses the .txt sidecars directly.")
        return
    for txt in sorted(glob.glob(os.path.join("voice", "samples", "*.txt"))):
        wav = os.path.splitext(txt)[0] + ".wav"
        with open(txt, encoding="utf-8") as f:
            tts.speak(f.read(), out_path=wav)
        print("wrote", wav)

if __name__ == "__main__":
    main()

"""Diagnostic timings for synthetic speech, without recording devices."""
from pathlib import Path
import json
import sys
import time
import wave
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from translator import paths
from translator.translation import LocalTranslation
from translator.audio import to_mono_16k
from translator.engine import uncommitted_words
from faster_whisper import WhisperModel

with wave.open(str(paths.ROOT / "diagnostics" / "sample.wav"), "rb") as wav:
    rate = wav.getframerate()
    raw = np.frombuffer(wav.readframes(wav.getnframes()), np.int16).reshape(-1, wav.getnchannels()).astype(np.float32) / 32768
fixture = np.concatenate([to_mono_16k(raw, rate), np.zeros(16000, np.float32)])
model = WhisperModel(str(paths.MODELS / "small.en"), device="cpu", compute_type="int8", cpu_threads=6, local_files_only=True)
translation = LocalTranslation(paths.MODELS)
last_end = -1.0
for start in range(0, 60, 4):
    indices = np.arange(round(start * 16000), round((start + 4.5) * 16000)) % len(fixture)
    before = time.perf_counter()
    segments, _ = model.transcribe(fixture[indices], language="en", beam_size=1, vad_filter=True,
        condition_on_previous_text=False, temperature=0.0, max_new_tokens=96,
        hallucination_silence_threshold=1, word_timestamps=True, vad_parameters={"min_silence_duration_ms": 300})
    segments = list(segments)
    print(json.dumps({"start": start, "asr_seconds": time.perf_counter()-before}), flush=True)
    for segment in segments:
        words = uncommitted_words(segment.words or [], start, last_end)
        if not words:
            continue
        original = "".join(w.word for w in words).strip()
        before = time.perf_counter()
        output = translation.translate(original)
        print(json.dumps({"input": original, "translation_seconds": time.perf_counter()-before, "output": output}), flush=True)
        last_end = start + words[-1].end

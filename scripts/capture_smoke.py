"""Short real WASAPI test. Reads microphone in memory, stores only metrics.

Plays a supplied synthetic fixture through the default output. The resulting
system transcript may be saved in the report; microphone speech is never saved.
"""
import argparse
import json
from pathlib import Path
import sys
import threading
import time
import winsound

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from translator import paths
from translator.audio import Capture, list_devices, audio_host
from faster_whisper import WhisperModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    system, microphones, default_system, default_mic = list_devices()
    devices = [(next(d for d in system if d.index == default_system), "Sistema"),
               (next(d for d in microphones if d.index == default_mic), "Micrófono")]
    stopped, paused = threading.Event(), threading.Event()
    chunks, errors = [], []
    levels = {"Sistema": [], "Micrófono": []}
    epoch = time.monotonic()
    def submit(chunk):
        if chunk.source == "Sistema":
            chunks.append(chunk)
    def level(source, value):
        levels[source].append(value)
    with audio_host() as manager:
        captures = [Capture(device, source, epoch, paused, stopped, submit, level, errors.append, manager)
                    for device, source in devices]
        for capture in captures:
            capture.start()
        for capture in captures:
            if not capture.ready.wait(15):
                errors.append(f"{capture.source}: stream did not become ready")
        time.sleep(.5)
        winsound.PlaySound(str(args.sample.resolve()), winsound.SND_FILENAME)
        time.sleep(1)
        stopped.set()
        for capture in captures:
            capture.join()
    text = []
    if chunks:
        model = WhisperModel(str(paths.MODELS / "base.en"), device="cpu", compute_type="int8", cpu_threads=6, local_files_only=True)
        for chunk in chunks:
            segments, _ = model.transcribe(chunk.samples, language="en", beam_size=1, vad_filter=True,
                temperature=0, max_new_tokens=96, condition_on_previous_text=False)
            text.extend(s.text.strip() for s in segments)
    success = not errors and not any(c.is_alive() for c in captures) and "hello" in " ".join(text).lower()
    report = {"success": success, "errors": errors, "devices": {source: device.name for device, source in devices},
              "sources": {source: {"audio_blocks": len(values), "peak_level": max(values, default=0)} for source, values in levels.items()},
              "system_chunks": len(chunks), "synthetic_system_transcript": " ".join(text),
              "microphone_audio_saved": False}
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report), flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

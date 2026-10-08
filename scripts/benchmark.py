"""Real-time paced synthetic sessions through the production ASR/translation engine.

This measures pipeline latency, not microphone recognition quality. The fixture
is synthetic English speech; no personal audio is captured or persisted.
"""
import argparse
from contextlib import nullcontext
from datetime import datetime
import json
from pathlib import Path
import socket
import sys
import threading
import time
import wave

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from translator import paths
from translator import engine as engine_module
from translator.audio import AudioChunk, to_mono_16k, MAX_BLOCK_SECONDS, OVERLAP_SECONDS
from PySide6.QtCore import QCoreApplication
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--models", nargs="+", choices=("small.en", "base.en"), default=["small.en", "base.en"])
    parser.add_argument("--block-seconds", type=float, help="Override block duration for a controlled comparison")
    args = parser.parse_args()
    with wave.open(str(args.sample), "rb") as wav:
        rate = wav.getframerate()
        if wav.getsampwidth() != 2:
            raise ValueError("Use a PCM 16-bit WAV test fixture")
        data = np.frombuffer(wav.readframes(wav.getnframes()), np.int16).reshape(-1, wav.getnchannels()).astype(np.float32) / 32768
    sample = to_mono_16k(data, rate)
    fixture = np.concatenate([sample, np.zeros(16000, np.float32)])
    app = QCoreApplication([])
    reports = []
    attempts = []
    def deny(*a, **kw):
        attempts.append(repr(a))
        raise RuntimeError("No network allowed in benchmark")
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    socket.getaddrinfo = deny

    class SyntheticCapture(threading.Thread):
        def __init__(self, device, source, epoch, paused, stopped, submit, level, error, manager=None):
            super().__init__(daemon=True)
            self.epoch, self.stopped, self.submit, self.source = epoch, stopped, submit, source
            self.played_until = 0
        def run(self):
            start = 0.0
            while start < args.seconds and not self.stopped.is_set():
                duration = args.block_seconds or self.block_seconds
                end = min(start + duration, args.seconds)
                remaining = self.epoch + end - time.monotonic()
                if remaining > 0 and self.stopped.wait(remaining):
                    break
                indices = np.arange(round(start * 16000), round(end * 16000)) % len(fixture)
                self.submit(AudioChunk(self.source, start, end, fixture[indices]))
                self.played_until = end
                if end == args.seconds:
                    break
                start += duration - OVERLAP_SECONDS
            self.stopped.set()

    engine_module.Capture = SyntheticCapture
    engine_module.audio_host = lambda: nullcontext(None)
    for model in args.models:
        print(f"Inicio de sesión sintética {model}: {args.seconds} segundos", flush=True)
        # Measure each model independently. Adaptive fallback is tested separately.
        engine = engine_module.Engine([(None, "Sistema")], model, adaptive=False)
        latency, timing, backlog, errors = [], [], [], []
        output_text = []
        ready_at = []
        finished = []
        def ready():
            ready_at.append(time.monotonic())
        def segment(seg):
            if ready_at:
                latency.append(time.monotonic() - ready_at[0] - seg.end)
            output_text.append(seg.original)
        engine.events.ready.connect(ready)
        engine.events.segment.connect(segment)
        engine.events.backlog.connect(backlog.append)
        engine.events.error.connect(errors.append)
        def timed(value):
            timing.append(value)
            if len(timing) <= 8:
                print(json.dumps(value), flush=True)
        engine.events.timing.connect(timed)
        engine.events.finished.connect(lambda: finished.append(True))
        engine.start()
        deadline = time.monotonic() + args.seconds + 180
        progress_at = time.monotonic() + 60
        while not finished and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
            if time.monotonic() >= progress_at:
                print(f"{model}: {len(output_text)} segmentos, pendiente {backlog[-1] if backlog else 0:.1f}s", flush=True)
                progress_at += 60
        if not finished:
            engine.stop()
            errors.append("Timeout")
        engine.thread.join(timeout=10)
        app.processEvents()
        report = {"model": model, "capture_block_seconds": args.block_seconds or (2.5 if model == "base.en" else 4.5), "synthetic_audio_seconds": args.seconds,
            "completed_synthetic_seconds": max((c.played_until for c in engine.captures), default=0),
            "segments": len(output_text), "errors": errors,
            "latency_median_seconds": round(float(np.median(latency)), 3) if latency else None,
            "latency_p95_seconds": round(float(np.percentile(latency, 95)), 3) if latency else None,
            "latency_max_seconds": round(max(latency), 3) if latency else None,
            "max_pending_audio_seconds": round(max(backlog), 3) if backlog else None,
            "final_pending_audio_seconds": round(engine.pending, 3),
            "first_transcript": output_text[0] if output_text else None,
            "last_transcript": output_text[-1] if output_text else None}
        report["timing"] = timing
        reports.append(report)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"completed": len(reports) == len(args.models) and all(r["completed_synthetic_seconds"] == args.seconds and not r["errors"] for r in reports), "network_attempts": attempts, "sessions": reports}, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return int(bool(attempts) or any(r["errors"] or not r["segments"] for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())

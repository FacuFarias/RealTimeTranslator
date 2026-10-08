"""Explicit command-line self-test of the portable build (no personal audio).

Usage: Traductor.exe --self-test --sample sample.wav --report report.json
Uses synthetic/provided audio only. All socket connections are denied during test.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import platform
import socket
import sys
import tempfile
import time
import traceback

from .paths import MODELS


def self_test(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--render-dir", type=Path)
    args = parser.parse_args(argv)
    report = {"platform": platform.platform(), "python": sys.version,
              "frozen": bool(getattr(sys, "frozen", False)), "models_path": str(MODELS),
              "embedded_runtime": (Path(sys.executable).parent / "runtime-manifest.json").exists(),
              "network_attempts": [], "tests": {}}
    def deny_network(*arguments, **kwargs):
        report["network_attempts"].append(repr(arguments))
        raise RuntimeError("Network connections are disabled during this self-test")
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    success = True
    try:
        from PySide6.QtWidgets import QApplication
        from .translation import LocalTranslation
        from .audio import list_devices
        from .session import Segment, export_text
        from .ui import MainWindow
        from faster_whisper import WhisperModel
        app = QApplication.instance() or QApplication([])
        translated = LocalTranslation(MODELS).translate("Hello. This application works without an internet connection.")
        assert translated and "aplic" in translated.lower()
        report["tests"]["translation"] = translated
        system, mic, default_system, default_mic = list_devices()
        report["tests"]["devices"] = {"system": [d.name for d in system], "microphones": [d.name for d in mic]}
        window = MainWindow()
        window.on_segment(Segment(1, "Sistema", 0, 2, "Hello. How are you?", "Hola. ¿Cómo estás?"))
        window.on_segment(Segment(2, "Micrófono", 2, 4, "This application works offline.", "Esta aplicación funciona sin conexión."))
        assert "Hola" in window.translated.toPlainText()
        window.subtitle.set_text("Sistema: Hola. ¿Cómo estás?\nMicrófono: Esta aplicación funciona sin conexión.")
        if args.render_dir:
            args.render_dir.mkdir(parents=True, exist_ok=True)
            window.show()
            window.subtitle.show()
            app.processEvents()
            assert window.grab().save(str(args.render_dir / "main-window.png"))
            assert window.subtitle.grab().save(str(args.render_dir / "subtitles.png"))
        window.dirty = False
        window.close()
        window.subtitle.hide()
        report["tests"]["gui"] = "ok"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sesión.txt"
            export_text(output, datetime.now(), window.segments)
            content = output.read_text(encoding="utf-8")
            assert "Español: Hola" in content and "Inglés: Hello" in content
            report["tests"]["export"] = "ok"
        report["tests"]["recognition"] = {}
        for name in ("small.en", "base.en"):
            started = time.perf_counter()
            model = WhisperModel(str(MODELS / name), device="cpu", compute_type="int8", cpu_threads=6, local_files_only=True)
            loaded = time.perf_counter() - started
            entry = {"load_seconds": round(loaded, 3)}
            if args.sample:
                started = time.perf_counter()
                segments, info = model.transcribe(str(args.sample), language="en", beam_size=1,
                    vad_filter=True, condition_on_previous_text=False, word_timestamps=True)
                entry["text"] = " ".join(s.text.strip() for s in segments)
                entry["inference_seconds"] = round(time.perf_counter() - started, 3)
                entry["audio_seconds"] = round(info.duration, 3)
                assert "hello" in entry["text"].lower()
            report["tests"]["recognition"][name] = entry
            del model
        assert not report["network_attempts"], "A library attempted to connect to the network"
    except Exception:
        success = False
        report["error"] = traceback.format_exc()
    report["success"] = success
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if success else 1

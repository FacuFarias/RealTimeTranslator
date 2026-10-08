import queue
import threading
import time

from PySide6.QtCore import QObject, Signal

from .paths import MODELS
from .audio import Capture, audio_host
from .session import Segment
from .translation import LocalTranslation


def uncommitted_words(words, chunk_start, boundary):
    """Drop words that started in committed context; allow 20ms alignment jitter."""
    return [word for word in words if chunk_start + word.start >= boundary - 0.02]


class Events(QObject):
    ready = Signal()
    segment = Signal(object)
    level = Signal(str, float)
    error = Signal(str)
    finished = Signal()
    backlog = Signal(float)
    timing = Signal(object)
    mode_changed = Signal(str)


class Engine:
    def __init__(self, devices, model, adaptive=True):
        self.events = Events()
        self.devices, self.model_name = devices, model
        self.adaptive = adaptive
        self.active_model = model
        self.paused, self.stopped = threading.Event(), threading.Event()
        self.chunks = queue.Queue()
        self.captures = []
        self.thread = threading.Thread(target=self.run, daemon=True, name="procesamiento")
        self.pending = 0.0
        self.lock = threading.Lock()
        self.last_end = {}
        self.sequence = 0
        self.host = None

    def start(self):
        self.thread.start()

    def stop(self):
        self.stopped.set()

    def submit(self, chunk):
        with self.lock:
            self.pending += chunk.end - chunk.start
            pending = self.pending
            self.chunks.put(chunk)
        self.events.backlog.emit(pending)
        if pending > 60 and not self.stopped.is_set():
            self.stopped.set()
            self.events.error.emit("La traducción lleva más de 60 segundos pendientes. Se detuvo la captura para procesar lo recibido. Prueba el modo rápido.")

    def capture_error(self, message):
        self.stopped.set()
        self.events.error.emit(message)

    def run(self):
        try:
            from faster_whisper import WhisperModel
            model_path = MODELS / self.model_name
            if not model_path.exists():
                raise RuntimeError("Faltan modelos locales. Conserva la carpeta models junto a Traductor.exe.")
            whisper = WhisperModel(str(model_path), device="cpu", compute_type="int8", cpu_threads=6, local_files_only=True)
            translation = LocalTranslation(MODELS)
            # Warm-up translation also checks all local auxiliary resources.
            translation.translate("Ready.")
            if self.stopped.is_set():
                return
            host = audio_host()
            manager = host.__enter__()
            self.host = host
            epoch = time.monotonic()
            for device, source in self.devices:
                capture = Capture(device, source, epoch, self.paused, self.stopped,
                                  self.submit, self.events.level.emit, self.capture_error, manager)
                self.captures.append(capture)
                capture.block_seconds = 2.5 if self.active_model == "base.en" else 4.5
                capture.silence_seconds = .35 if self.active_model == "base.en" else .6
                capture.start()
            for capture in self.captures:
                ready = getattr(capture, "ready", None)
                while ready is not None and not ready.wait(.05) and capture.is_alive() and not self.stopped.is_set():
                    pass
            if not self.stopped.is_set():
                self.events.ready.emit()
            while True:
                if self.stopped.is_set() and not any(c.is_alive() for c in self.captures) and self.chunks.empty():
                    break
                try:
                    chunk = self.chunks.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    began = time.perf_counter()
                    translation_seconds = 0.0
                    with self.lock:
                        pending = self.pending
                    if self.adaptive and self.active_model == "small.en" and pending > 18:
                        whisper = WhisperModel(str(MODELS / "base.en"), device="cpu", compute_type="int8", cpu_threads=6, local_files_only=True)
                        self.active_model = "base.en"
                        for capture in self.captures:
                            capture.block_seconds = 2.5
                            capture.silence_seconds = .35
                        self.events.mode_changed.emit("base.en")
                    segments, _ = whisper.transcribe(chunk.samples, language="en", task="transcribe",
                        beam_size=1, vad_filter=True, condition_on_previous_text=False,
                        temperature=0.0, max_new_tokens=96, hallucination_silence_threshold=1.0,
                        word_timestamps=True, vad_parameters={"min_silence_duration_ms": 300})
                    for result in segments:
                        boundary = self.last_end.get(chunk.source, -1.0)
                        # A clipped context word can have a midpoint beyond the
                        # previous boundary. Its start still identifies overlap.
                        words = uncommitted_words(result.words or [], chunk.start, boundary)
                        if not words:
                            continue
                        original = "".join(word.word for word in words).strip()
                        if not original:
                            continue
                        start = chunk.start + words[0].start
                        end = chunk.start + words[-1].end
                        try:
                            translation_began = time.perf_counter()
                            translated = translation.translate(original)
                            translation_seconds += time.perf_counter() - translation_began
                        except Exception as exc:
                            translated = "[No se pudo traducir este segmento; se conserva el original.]"
                            self.capture_error(f"No se pudo traducir un segmento: {exc}. Se conservó la transcripción y se detuvo la captura.")
                        self.sequence += 1
                        self.last_end[chunk.source] = end
                        self.events.segment.emit(Segment(self.sequence, chunk.source, start, end, original, translated))
                except Exception as exc:
                    self.capture_error(f"No se pudo transcribir el audio entre {chunk.start:.1f} y {chunk.end:.1f} s de {chunk.source}: {exc}. Se detuvo la captura; se procesará el resto pendiente.")
                finally:
                    self.events.timing.emit({"source": chunk.source, "start": chunk.start,
                        "asr_seconds": time.perf_counter() - began - translation_seconds,
                        "translation_seconds": translation_seconds})
                    with self.lock:
                        self.pending = max(0, self.pending - (chunk.end - chunk.start))
                        pending = self.pending
                    self.events.backlog.emit(pending)
        except Exception as exc:
            self.stopped.set()
            self.events.error.emit(f"No se pudo procesar la sesión: {exc}")
        finally:
            self.stopped.set()
            for capture in self.captures:
                capture.join()
            try:
                if self.host is not None:
                    self.host.__exit__(None, None, None)
                    self.host = None
            finally:
                self.events.finished.emit()

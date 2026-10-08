"""Audio buffers never touch disk. Each device has an independent stream."""
from dataclasses import dataclass
from contextlib import contextmanager, nullcontext
import math
import threading
import time

import numpy as np
import pyaudiowpatch as pa
from scipy.signal import resample_poly

# PortAudio initialization, termination and stream creation are not thread-safe.
# Reading distinct streams can run in parallel; lifecycle operations must not.
_CONTROL_LOCK = threading.RLock()
MAX_BLOCK_SECONDS = 4.5
OVERLAP_SECONDS = .5


@contextmanager
def audio_host():
    with _CONTROL_LOCK:
        context = pa.PyAudio()
        manager = context.__enter__()
    try:
        yield manager
    finally:
        with _CONTROL_LOCK:
            context.__exit__(None, None, None)


@contextmanager
def input_stream(manager, **kwargs):
    with _CONTROL_LOCK:
        context = manager.open(**kwargs)
        stream = context.__enter__()
    try:
        yield stream
    finally:
        with _CONTROL_LOCK:
            context.__exit__(None, None, None)


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    rate: int
    channels: int
    loopback: bool


def list_devices():
    with audio_host() as audio:
        api = audio.get_host_api_info_by_type(pa.paWASAPI)
        system, microphones = [], []
        try:
            default_loopback = audio.get_wasapi_loopback_analogue_by_index(api["defaultOutputDevice"])
            default_system = int(default_loopback["index"])
        except (OSError, ValueError, LookupError):
            default_system = -1
        for info in audio.get_device_info_generator():
            if info["hostApi"] != api["index"] or info["maxInputChannels"] < 1:
                continue
            device = Device(int(info["index"]), info["name"], round(info["defaultSampleRate"]), int(info["maxInputChannels"]), bool(info.get("isLoopbackDevice")))
            (system if device.loopback else microphones).append(device)
        return system, microphones, default_system, int(api["defaultInputDevice"])


def to_mono_16k(data: np.ndarray, rate: int) -> np.ndarray:
    mono = data.mean(axis=1) if data.ndim == 2 else data
    common = math.gcd(rate, 16000)
    return np.asarray(resample_poly(mono, 16000 // common, rate // common), dtype=np.float32)


@dataclass
class AudioChunk:
    source: str
    start: float
    end: float
    samples: np.ndarray


class Capture(threading.Thread):
    def __init__(self, device, source, epoch, paused, stopped, submit, level, error, manager=None):
        super().__init__(name=f"captura-{source}", daemon=True)
        self.device, self.source, self.epoch = device, source, epoch
        self.paused, self.stopped = paused, stopped
        self.submit, self.level, self.error = submit, level, error
        self.manager = manager
        self.ready = threading.Event()
        self.block_seconds = MAX_BLOCK_SECONDS
        self.silence_seconds = .6

    def run(self):
        blocks = []
        start = None
        frames = 0
        fresh_frames = 0
        silence = 0
        was_paused = False
        # Read 100 ms packets; the engine selects phrase/pause limits by mode.
        blocksize = self.device.rate // 10
        try:
            with (audio_host() if self.manager is None else nullcontext(self.manager)) as audio:
                with input_stream(audio, format=pa.paFloat32, channels=self.device.channels,
                                rate=self.device.rate, input=True,
                                input_device_index=self.device.index,
                                frames_per_buffer=blocksize) as stream:
                    self.ready.set()
                    while not self.stopped.is_set():
                        if hasattr(stream, "is_active") and not stream.is_active():
                            raise OSError("El dispositivo está inactivo o desconectado")
                        # Loopback endpoints may stop producing packets when idle.
                        # Poll availability so Stop never waits on an idle read.
                        if hasattr(stream, "get_read_available") and stream.get_read_available() < blocksize:
                            self.stopped.wait(.01)
                            continue
                        raw = stream.read(blocksize, exception_on_overflow=True)
                        samples = np.frombuffer(raw, np.float32).reshape(-1, self.device.channels)
                        now = time.monotonic() - self.epoch
                        mono = samples.mean(axis=1)
                        rms = float(np.sqrt(np.mean(mono * mono)))
                        self.level(self.source, min(1.0, rms * 8))
                        if self.paused.is_set():
                            if not was_paused and blocks and fresh_frames:
                                self.flush(blocks, start, frames)
                            blocks, start, frames, silence = [], None, 0, 0
                            fresh_frames = 0
                            was_paused = True
                            continue
                        was_paused = False
                        if start is None:
                            start = max(0, now - len(samples) / self.device.rate)
                        blocks.append(samples.copy())
                        frames += len(samples)
                        fresh_frames += len(samples)
                        silence = silence + len(samples) if rms < 0.008 else 0
                        if frames >= self.device.rate * self.block_seconds:
                            self.flush(blocks, start, frames)
                            # Retain 500ms context, timestamps let ASR suppress repeats.
                            tail = np.concatenate(blocks)[-round(self.device.rate * OVERLAP_SECONDS):].copy()
                            start += (frames - len(tail)) / self.device.rate
                            blocks, frames, silence = [tail], len(tail), 0
                            fresh_frames = 0
                        elif silence >= self.device.rate * self.silence_seconds:
                            self.flush(blocks, start, frames)
                            blocks, start, frames, silence = [], None, 0, 0
                            fresh_frames = 0
                    if blocks and fresh_frames:
                        self.flush(blocks, start, frames)
        except Exception as exc:
            if blocks and fresh_frames:
                self.flush(blocks, start, frames)
            self.error(f"No se pudo capturar {self.source}: {exc}. Revisa el dispositivo y los permisos de audio de Windows.")
        finally:
            self.level(self.source, 0)

    def flush(self, blocks, start, frames):
        if not blocks:
            return
        samples = to_mono_16k(np.concatenate(blocks), self.device.rate)
        # Skip silence; VAD inside ASR handles quieter speech/non-speech sounds.
        if float(np.max(np.abs(samples))) < 0.003:
            return
        self.submit(AudioChunk(self.source, start, start + frames / self.device.rate, samples))

import threading
from types import SimpleNamespace
import numpy as np
import pytest

from translator import audio


@pytest.mark.parametrize("block_seconds, bounds", [(4.5, [(0, 4.5), (4, 7.5)]),
    (2.5, [(0, 2.5), (2, 4.5), (4, 6.5), (6, 7.5)])])
def test_capture_splits_long_speech_keeps_overlap_and_flushes_stop(monkeypatch, block_seconds, bounds):
    stopped, paused = threading.Event(), threading.Event()
    rate = 16000
    block = np.full((1600, 1), .1, np.float32).tobytes()
    ticks = [0]
    chunks, levels, errors = [], [], []
    class Stream:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size, **kwargs):
            ticks[0] += 1
            if ticks[0] == 75:
                stopped.set()
            return block
    class PyAudio:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def open(self, **kwargs):
            return Stream()
    monkeypatch.setattr(audio.pa, "PyAudio", PyAudio)
    monkeypatch.setattr(audio.time, "monotonic", lambda: ticks[0] * .1)
    device = audio.Device(0, "Test", rate, 1, False)
    capture = audio.Capture(device, "Sistema", 0, paused, stopped, chunks.append,
                  lambda *value: levels.append(value), errors.append)
    capture.block_seconds = block_seconds
    capture.run()
    assert not errors
    assert [(chunk.start, chunk.end) for chunk in chunks] == bounds
    for chunk in chunks:
        assert len(chunk.samples) == round((chunk.end - chunk.start) * rate)


def test_pause_flushes_previous_audio_and_excludes_paused_samples(monkeypatch):
    stopped, paused = threading.Event(), threading.Event()
    rate = 16000
    ticks = [0]
    chunks, errors = [], []
    class Stream:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size, **kwargs):
            ticks[0] += 1
            if ticks[0] == 11:
                paused.set()
            if ticks[0] == 21:
                paused.clear()
            if ticks[0] == 30:
                stopped.set()
            return np.full((1600, 1), .8 if paused.is_set() else .1, np.float32).tobytes()
    class PyAudio:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def open(self, **kwargs):
            return Stream()
    monkeypatch.setattr(audio.pa, "PyAudio", PyAudio)
    monkeypatch.setattr(audio.time, "monotonic", lambda: ticks[0] * .1)
    audio.Capture(audio.Device(0, "Test", rate, 1, False), "Micrófono", 0,
        paused, stopped, chunks.append, lambda *args: None, errors.append).run()
    assert not errors
    assert len(chunks) == 2
    assert chunks[0].end == 1
    assert chunks[1].start == 2
    assert np.max(chunks[1].samples) < .2


def test_disconnection_flushes_audio_already_captured(monkeypatch):
    stopped, paused = threading.Event(), threading.Event()
    calls = [0]
    chunks, errors = [], []
    class Stream:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size, **kwargs):
            calls[0] += 1
            if calls[0] > 3:
                raise OSError("device disconnected")
            return np.full((1600, 1), .1, np.float32).tobytes()
    class PyAudio:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def open(self, **kwargs):
            return Stream()
    monkeypatch.setattr(audio.pa, "PyAudio", PyAudio)
    audio.Capture(audio.Device(0, "Test", 16000, 1, False), "Micrófono", 0,
        paused, stopped, chunks.append, lambda *args: None, errors.append).run()
    assert len(chunks) == 1
    assert len(chunks[0].samples) == 4800
    assert "device disconnected" in errors[0]


def test_portaudio_initialization_serialized_but_stream_lifetimes_parallel(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import time
    state = {"initializing": 0, "peak": 0}
    start = threading.Barrier(3)
    opened = threading.Barrier(2)
    class PyAudio:
        def __init__(self):
            state["initializing"] += 1
            state["peak"] = max(state["peak"], state["initializing"])
            time.sleep(.04)
            state["initializing"] -= 1
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(audio.pa, "PyAudio", PyAudio)
    def open_host():
        start.wait(timeout=2)
        with audio.audio_host():
            opened.wait(timeout=2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(open_host) for _ in range(2)]
        start.wait(timeout=2)
        for task in tasks:
            task.result(timeout=3)
    assert state["peak"] == 1


def test_idle_loopback_can_stop_without_blocking_read(monkeypatch):
    stopped, paused = threading.Event(), threading.Event()
    errors = []
    class Stream:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get_read_available(self):
            return 0
        def read(self, *args, **kwargs):
            raise AssertionError("Idle read would block")
    class PyAudio:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def open(self, **kwargs):
            return Stream()
    monkeypatch.setattr(audio.pa, "PyAudio", PyAudio)
    capture = audio.Capture(audio.Device(0, "Idle", 16000, 1, True), "Sistema", 0,
        paused, stopped, lambda *args: None, lambda *args: None, errors.append)
    capture.start()
    assert capture.ready.wait(1)
    stopped.set()
    capture.join(timeout=1)
    assert not capture.is_alive()
    assert not errors

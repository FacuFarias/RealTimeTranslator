from types import SimpleNamespace
import numpy as np
import pytest

from translator.audio import AudioChunk, to_mono_16k
from translator.engine import Engine, uncommitted_words


def word(text, start, end):
    return SimpleNamespace(word=text, start=start, end=end)


def test_overlap_keeps_new_speech_without_repeating_context():
    words = [word("previous", 0, .4), word("new", .6, 1.2), word("phrase", 1.3, 2)]
    kept = uncommitted_words(words, 4.5, 5.0)
    assert [w.word for w in kept] == ["new", "phrase"]
    assert [w.word for w in uncommitted_words(words, 4.5, -1)] == ["previous", "new", "phrase"]


def test_clipped_context_word_is_not_repeated_and_real_repetition_is_kept():
    words = [word(" computer.", 0, .4), word(" Next", .45, .8)]
    assert [w.word for w in uncommitted_words(words, 56, 56.04)] == [" Next"]
    repeated = [word(" no", .1, .3), word(" no", .4, .6)]
    assert len(uncommitted_words(repeated, 10, 10)) == 2


def test_resample_stereo_and_preserve_duration():
    rate = 48000
    tone = np.sin(2 * np.pi * 220 * np.arange(rate) / rate).astype(np.float32)
    result = to_mono_16k(np.column_stack((tone, tone)), rate)
    assert result.shape == (16000,)
    assert result.dtype == np.float32
    assert .68 < np.sqrt(np.mean(result ** 2)) < .73


def test_backlog_stops_without_discarding_already_received_chunks():
    engine = Engine([], "base.en")
    for n in range(13):
        engine.submit(AudioChunk("Sistema", n * 5, n * 5 + 5, np.zeros(80000, np.float32)))
    assert engine.stopped.is_set()
    assert engine.chunks.qsize() == 13
    assert engine.pending == 65


def test_microphone_remains_available_without_default_loopback(monkeypatch):
    from translator import audio
    class PyAudio:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get_host_api_info_by_type(self, kind):
            return {"index": 0, "defaultOutputDevice": 1, "defaultInputDevice": 0}
        def get_wasapi_loopback_analogue_by_index(self, index):
            raise LookupError("No loopback available")
        def get_device_info_generator(self):
            yield {"index": 0, "name": "Mic", "hostApi": 0, "maxInputChannels": 1, "defaultSampleRate": 16000}
    monkeypatch.setattr(audio.pa, "PyAudio", PyAudio)
    system, microphones, default_system, default_mic = audio.list_devices()
    assert not system
    assert [d.name for d in microphones] == ["Mic"]
    assert default_system == -1 and default_mic == 0


def test_stop_drains_queue_and_deduplicates_each_source(monkeypatch):
    from translator import engine as module
    import faster_whisper
    emitted = []
    class Whisper:
        def __init__(self, *args, **kwargs):
            pass
        def transcribe(self, samples, **kwargs):
            return [SimpleNamespace(words=[word(" Hello", 0, .4), word(" world.", .6, 1.0)])], None
    class Translation:
        def __init__(self, *args):
            pass
        def translate(self, text):
            return "Hola mundo."
    class Capture:
        def __init__(self, *args):
            pass
        def start(self):
            # One full chunk, one overlapping chunk, then a microphone chunk.
            e.submit(AudioChunk("Sistema", 0, 1, np.zeros(16000, np.float32)))
            e.submit(AudioChunk("Sistema", .5, 1.5, np.zeros(16000, np.float32)))
            e.submit(AudioChunk("Micrófono", 0, 1, np.zeros(16000, np.float32)))
            e.stop()
        def is_alive(self):
            return False
        def join(self, **kwargs):
            pass
    monkeypatch.setattr(faster_whisper, "WhisperModel", Whisper)
    monkeypatch.setattr(module, "LocalTranslation", Translation)
    monkeypatch.setattr(module, "Capture", Capture)
    from contextlib import nullcontext
    monkeypatch.setattr(module, "audio_host", lambda: nullcontext(None))
    monkeypatch.setattr(module, "MODELS", __import__("pathlib").Path(__file__).parent)
    e = Engine([(None, "Sistema")], ".")
    e.events.segment.connect(emitted.append)
    e.run()
    assert [s.original for s in emitted] == ["Hello world.", "world.", "Hello world."]
    assert [s.source for s in emitted] == ["Sistema", "Sistema", "Micrófono"]
    assert e.pending == 0


@pytest.mark.parametrize("adaptive", [True, False])
def test_adaptive_mode_preserves_every_queued_chunk(monkeypatch, tmp_path, adaptive):
    from contextlib import nullcontext
    from pathlib import Path
    from translator import engine as module
    import faster_whisper
    (tmp_path / "small.en").mkdir()
    (tmp_path / "base.en").mkdir()
    loads, emitted, changes = [], [], []
    class Whisper:
        def __init__(self, path, **kwargs):
            loads.append(Path(path).name)
        def transcribe(self, samples, **kwargs):
            return [SimpleNamespace(words=[word(" Hello.", 0, .4)])], None
    class Translation:
        def __init__(self, *args):
            pass
        def translate(self, text):
            return "Hola."
    class Capture:
        def __init__(self, *args):
            pass
        def start(self):
            for n in range(6):
                engine.submit(AudioChunk("Sistema", n * 4, n * 4 + 4.5, np.zeros(72000, np.float32)))
            engine.stop()
        def is_alive(self):
            return False
        def join(self, **kwargs):
            pass
    monkeypatch.setattr(faster_whisper, "WhisperModel", Whisper)
    monkeypatch.setattr(module, "LocalTranslation", Translation)
    monkeypatch.setattr(module, "Capture", Capture)
    monkeypatch.setattr(module, "MODELS", tmp_path)
    monkeypatch.setattr(module, "audio_host", lambda: nullcontext(None))
    engine = Engine([(None, "Sistema")], "small.en", adaptive=adaptive)
    engine.events.segment.connect(emitted.append)
    engine.events.mode_changed.connect(changes.append)
    engine.run()
    assert len(emitted) == 6 and engine.pending == 0
    assert loads == (["small.en", "base.en"] if adaptive else ["small.en"])
    assert changes == (["base.en"] if adaptive else [])

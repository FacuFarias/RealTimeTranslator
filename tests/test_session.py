from datetime import datetime
from translator.session import Segment, export_text, timestamp


def test_timestamp_rounding_and_long_session():
    assert timestamp(59.9996) == "00:01:00.000"
    assert timestamp(3601.125) == "01:00:01.125"
    assert timestamp(-1) == "00:00:00.000"


def test_export_both_languages_sources_and_temporal_order(tmp_path):
    output = tmp_path / "sesión.txt"
    segments = [Segment(1, "Sistema", 5, 6, "Good morning.", "Buenos días."),
                Segment(2, "Micrófono", 2, 3, "Hello.", "Hola.")]
    export_text(output, datetime(2026, 10, 8, 12), segments)
    text = output.read_text(encoding="utf-8")
    assert text.index("Micrófono") < text.index("Sistema")
    assert "Inglés: Good morning." in text
    assert "Español: Buenos días." in text
    assert "00:00:02.000 — 00:00:03.000" in text
    assert not output.with_name(output.name + ".tmp").exists()


def test_failed_export_preserves_existing_file(tmp_path, monkeypatch):
    from pathlib import Path
    output = tmp_path / "session.txt"
    output.write_text("previous export", encoding="utf-8")
    def fail(*args, **kwargs):
        raise OSError("disk failure")
    monkeypatch.setattr(Path, "replace", fail)
    import pytest
    with pytest.raises(OSError):
        export_text(output, datetime.now(), [])
    assert output.read_text() == "previous export"

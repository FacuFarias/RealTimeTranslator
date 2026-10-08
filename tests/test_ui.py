import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from translator.session import Segment
from translator import ui


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch):
    monkeypatch.setattr(ui, "list_devices", lambda: ([], [], -1, -1))
    window = ui.MainWindow()
    yield window
    window.dirty = False
    window.engine = None
    window.close()
    window.subtitle.hide()


def test_out_of_order_sources_are_displayed_and_saved_in_order(window, monkeypatch, tmp_path):
    window.on_segment(Segment(1, "Sistema", 5, 6, "Later.", "Después."))
    window.on_segment(Segment(2, "Micrófono", 1, 2, "Earlier.", "Antes."))
    assert window.original.toPlainText().index("Earlier") < window.original.toPlainText().index("Later")
    output = tmp_path / "session.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(output), ""))
    assert window.save()
    assert "Español: Antes." in output.read_text(encoding="utf-8")
    assert not window.dirty


def test_cancel_preserves_session_and_save_cancel_does_not_discard(window, monkeypatch):
    window.on_segment(Segment(1, "Sistema", 0, 1, "Hello.", "Hola."))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    assert not window.discard_allowed()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    assert not window.discard_allowed()
    assert window.dirty and len(window.segments) == 1


def test_no_source_reports_message_without_starting_engine(window, monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    window.start()
    assert window.engine is None
    assert messages


def test_pause_resume_and_stop_state(window):
    import threading
    class FakeEngine:
        paused = threading.Event()
        def stop(self):
            self.was_stopped = True
    window.engine = FakeEngine()
    window.pause()
    assert window.engine.paused.is_set() and window.pause_button.text() == "Reanudar"
    window.pause()
    assert not window.engine.paused.is_set() and window.pause_button.text() == "Pausar"
    window.stop()
    assert window.engine.was_stopped
    assert not window.stop_button.isEnabled()
    window.on_finished()
    assert window.start_button.isEnabled()


def test_subtitle_plain_text_and_controls(window):
    window.subtitle.set_text("<b>Recognized speech</b>")
    from PySide6.QtCore import Qt
    assert window.subtitle.label.textFormat() == Qt.TextFormat.PlainText
    window.font_size.setValue(30)
    assert window.subtitle.label.font().pointSize() == 30
    window.opacity.setValue(70)
    assert abs(window.subtitle.windowOpacity() - .7) < .01


def test_subtitles_grow_for_wrapped_translation(window, app):
    window.subtitle.resize(500, 160)
    window.subtitle.set_font(32)
    window.subtitle.set_text("Sistema: Esta aplicación traduce todo el audio del inglés al español.\nMicrófono: Los subtítulos se adaptan cuando una frase ocupa varias líneas.")
    window.subtitle.show()
    app.processEvents()
    assert window.subtitle.height() > 160
    assert window.subtitle.minimumHeight() <= window.subtitle.height()

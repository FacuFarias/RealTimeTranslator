from datetime import datetime
from pathlib import Path
import time

from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QCloseEvent, QTextCursor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QCheckBox, QComboBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QPlainTextEdit, QProgressBar,
    QSlider, QSpinBox, QFileDialog, QMessageBox, QGroupBox, QSplitter,
)

from .audio import list_devices
from .engine import Engine
from .session import export_text, timestamp


class Subtitles(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Subtítulos — arrastra la barra para mover")
        self.resize(900, 160)
        self.setMinimumSize(350, 100)
        self.recent_segments = []
        self.original_button = QPushButton("Mostrar original")
        self.original_button.setCheckable(True)
        self.original_button.toggled.connect(self.render_segments)
        self.label = QLabel("La traducción aparecerá aquí.")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.addWidget(self.original_button, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.label)
        self.setStyleSheet("Subtitles { background: #17202d; } QLabel { color: #ffffff; background: #17202d; }")
        self.set_font(25)

    def set_font(self, size):
        font = self.label.font()
        font.setPointSize(size)
        self.label.setFont(font)
        self.fit_height()

    def set_text(self, text):
        self.recent_segments = []
        self.display_text(text)

    def set_segments(self, segments):
        self.recent_segments = list(segments[-4:])
        self.render_segments()

    def render_segments(self, checked=None):
        original = self.original_button.isChecked()
        self.original_button.setText("Mostrar traducción" if original else "Mostrar original")
        if self.recent_segments:
            field = "original" if original else "translated"
            self.display_text("\n".join(getattr(segment, field) for segment in self.recent_segments))

    def display_text(self, text):
        # Plain text prevents markup in recognized speech from changing the UI.
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setText(text)
        self.fit_height()

    def fit_height(self):
        if not hasattr(self, "label"):
            return
        available = self.screen().availableGeometry()
        bounds = self.label.fontMetrics().boundingRect(
            QRect(0, 0, max(100, self.width() - 40), 10000),
            int(Qt.TextFlag.TextWordWrap), self.label.text())
        needed = max(100, min(bounds.height() + 32 + self.original_button.sizeHint().height() + self.layout().spacing(), available.height() - 80))
        if self.minimumHeight() != needed:
            self.setMinimumHeight(needed)
        if self.isVisible() and self.frameGeometry().bottom() > available.bottom():
            self.move(self.x(), max(available.top(), available.bottom() - self.frameGeometry().height()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_height()

    def closeEvent(self, event):
        self.hide()
        event.ignore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Traductor local · Inglés → Español")
        self.resize(1120, 780)
        self.engine = None
        self.segments = []
        self.dirty = False
        self.created = datetime.now()
        self.elapsed = 0
        self.last_tick = time.monotonic()
        self.recording = False
        self.paused = False
        self.closing = False
        self.subtitle = Subtitles()
        self.subtitle_lines = []
        self.subtitle_positioned = False

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        heading = QLabel("Traduce lo que escuchas")
        heading_color = "#83c5ff" if self.palette().window().color().lightness() < 128 else "#164c80"
        heading.setStyleSheet(f"font-size: 26px; font-weight: 600; color: {heading_color};")
        layout.addWidget(heading)
        description = QLabel("Inglés → español · Procesamiento local · Solo se guardan textos")
        layout.addWidget(description)

        group = QGroupBox("Fuentes de audio")
        grid = QGridLayout(group)
        self.system_enabled = QCheckBox("Audio del sistema")
        self.system_enabled.setChecked(True)
        self.mic_enabled = QCheckBox("Micrófono")
        self.system_devices = QComboBox()
        self.mic_devices = QComboBox()
        self.system_meter, self.mic_meter = QProgressBar(), QProgressBar()
        for meter in (self.system_meter, self.mic_meter):
            meter.setRange(0, 100)
            meter.setTextVisible(False)
            meter.setMaximumWidth(180)
        self.refresh = QPushButton("Actualizar dispositivos")
        self.refresh.clicked.connect(self.refresh_devices)
        grid.addWidget(self.system_enabled, 0, 0)
        grid.addWidget(self.system_devices, 0, 1)
        grid.addWidget(self.system_meter, 0, 2)
        grid.addWidget(self.mic_enabled, 1, 0)
        grid.addWidget(self.mic_devices, 1, 1)
        grid.addWidget(self.mic_meter, 1, 2)
        grid.addWidget(self.refresh, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
        note = QLabel("Selecciona la salida por la que reproduce tu aplicación. Para usar ambas fuentes, se recomiendan auriculares para evitar eco.")
        note.setWordWrap(True)
        grid.addWidget(note, 3, 0, 1, 3)
        grid.setColumnStretch(1, 1)
        layout.addWidget(group)

        settings = QHBoxLayout()
        settings.addWidget(QLabel("Modo:"))
        self.model = QComboBox()
        self.model.addItem("Estándar · mayor precisión", "small.en")
        self.model.addItem("Rápido · menor retraso", "base.en")
        self.model.setCurrentIndex(1)
        settings.addWidget(self.model)
        self.show_subtitles = QCheckBox("Subtítulos flotantes")
        self.show_subtitles.setChecked(True)
        self.show_subtitles.toggled.connect(self.toggle_subtitles)
        settings.addWidget(self.show_subtitles)
        settings.addWidget(QLabel("Letra:"))
        self.font_size = QSpinBox()
        self.font_size.setRange(14, 48)
        self.font_size.setValue(25)
        self.font_size.valueChanged.connect(self.subtitle.set_font)
        settings.addWidget(self.font_size)
        settings.addWidget(QLabel("Opacidad:"))
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(35, 100)
        self.opacity.setValue(95)
        self.opacity.setMaximumWidth(110)
        self.opacity.valueChanged.connect(lambda value: self.subtitle.setWindowOpacity(value / 100))
        self.subtitle.setWindowOpacity(.95)
        settings.addWidget(self.opacity)
        layout.addLayout(settings)
        self.adaptive = QCheckBox("Priorizar velocidad si aumenta el retraso")
        self.adaptive.setChecked(True)
        self.adaptive.setToolTip("Cambia automáticamente al modo Rápido cuando se acumula audio pendiente, conservando todos los segmentos recibidos.")
        layout.addWidget(self.adaptive)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Iniciar")
        self.start_button.setStyleSheet("background: #176ab2; color: white; padding: 9px 25px; font-weight: 600;")
        self.pause_button = QPushButton("Pausar")
        self.stop_button = QPushButton("Detener")
        self.save_button = QPushButton("Guardar textos")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.pause_button.clicked.connect(self.pause)
        self.stop_button.clicked.connect(self.stop)
        self.save_button.clicked.connect(self.save)
        for button in (self.start_button, self.pause_button, self.stop_button, self.save_button):
            controls.addWidget(button)
        controls.addStretch()
        self.duration = QLabel("00:00:00")
        controls.addWidget(self.duration)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.original, self.translated = QPlainTextEdit(), QPlainTextEdit()
        for title, editor in (("Transcripción · inglés", self.original), ("Traducción · español", self.translated)):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.addWidget(QLabel(title))
            editor.setReadOnly(True)
            editor.setPlaceholderText("Inicia una sesión para ver el texto aquí.")
            editor.setStyleSheet("font-size: 15px; padding: 10px;")
            panel_layout.addWidget(editor)
            splitter.addWidget(panel)
        layout.addWidget(splitter, stretch=1)
        self.status = QLabel("Listo para iniciar. La traducción aparece por frases, con unos segundos de retraso.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.backlog = QLabel("Pendiente: 0 s")
        layout.addWidget(self.backlog)
        self.locked_controls = [self.system_enabled, self.mic_enabled, self.system_devices, self.mic_devices, self.refresh, self.model, self.adaptive]
        self.refresh_devices()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)

    def refresh_devices(self):
        try:
            system, microphones, default_system, default_mic = list_devices()
            for combo, devices, default in ((self.system_devices, system, default_system), (self.mic_devices, microphones, default_mic)):
                previous = combo.currentData()
                previous_name = previous.name if previous else None
                combo.clear()
                for device in devices:
                    combo.addItem(device.name, device)
                chosen = next((i for i, d in enumerate(devices) if d.name == previous_name),
                              next((i for i, d in enumerate(devices) if d.index == default), 0))
                if devices:
                    combo.setCurrentIndex(chosen)
            self.status.setText("Listo para iniciar. Solo se captura audio mientras la sesión está activa.")
        except Exception as exc:
            self.status.setText(f"No se pudieron listar los dispositivos: {exc}. Conecta un dispositivo y pulsa Actualizar dispositivos.")

    def discard_allowed(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Textos sin guardar", "Hay textos sin guardar. ¿Quieres guardarlos antes de continuar?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return True

    def start(self):
        if self.engine is not None or not self.discard_allowed():
            return
        devices = []
        if self.system_enabled.isChecked() and self.system_devices.currentData():
            devices.append((self.system_devices.currentData(), "Sistema"))
        if self.mic_enabled.isChecked() and self.mic_devices.currentData():
            devices.append((self.mic_devices.currentData(), "Micrófono"))
        if not devices:
            QMessageBox.information(self, "Selecciona una fuente", "Activa al menos una fuente de audio con un dispositivo disponible.")
            return
        if self.system_enabled.isChecked() and not self.system_devices.currentData() or self.mic_enabled.isChecked() and not self.mic_devices.currentData():
            QMessageBox.information(self, "Dispositivo no disponible", "Una fuente activada no tiene dispositivo. Actualiza los dispositivos o desactiva esa fuente.")
            return
        self.created = datetime.now()
        self.segments.clear()
        self.dirty = False
        self.original.clear()
        self.translated.clear()
        self.subtitle_lines.clear()
        self.subtitle.set_text("Preparando modelos locales…")
        self.elapsed = 0
        self.duration.setText("00:00:00")
        self.paused = False
        self.pause_button.setText("Pausar")
        self.start_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        for control in self.locked_controls:
            control.setEnabled(False)
        self.status.setText("Cargando modelos locales. La captura comienza cuando estén listos…")
        self.engine = Engine(devices, self.model.currentData(), adaptive=self.adaptive.isChecked())
        events = self.engine.events
        events.ready.connect(self.on_ready)
        events.segment.connect(self.on_segment)
        events.level.connect(self.on_level)
        events.error.connect(self.on_error)
        events.finished.connect(self.on_finished)
        events.mode_changed.connect(self.on_mode_changed)
        events.backlog.connect(lambda pending: self.backlog.setText(f"Pendiente: {pending:.1f} s"))
        self.toggle_subtitles(self.show_subtitles.isChecked())
        self.engine.start()

    def on_ready(self):
        if not self.engine or self.engine.stopped.is_set():
            return
        self.recording = True
        self.last_tick = time.monotonic()
        self.pause_button.setEnabled(True)
        self.status.setText("Escuchando · Inglés → español · Procesamiento local")
        self.subtitle.set_text("Escuchando…")

    def pause(self):
        if not self.engine:
            return
        self.paused = not self.paused
        if self.paused:
            self.engine.paused.set()
        else:
            self.engine.paused.clear()
        self.pause_button.setText("Reanudar" if self.paused else "Pausar")
        self.status.setText("En pausa. Se termina de traducir el audio anterior." if self.paused else "Escuchando · Inglés → español")
        self.last_tick = time.monotonic()

    def stop(self):
        if self.engine:
            self.engine.stop()
            self.recording = False
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.status.setText("Captura detenida. Terminando de traducir los segmentos pendientes…")

    def on_error(self, message):
        self.recording = False
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.status.setText(message)
        QMessageBox.warning(self, "Aviso de la sesión", message)

    def on_finished(self):
        self.recording = False
        self.engine = None
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.save_button.setEnabled(bool(self.segments))
        for control in self.locked_controls:
            control.setEnabled(True)
        if not self.status.text().startswith(("No se", "La traducción")):
            self.status.setText("Sesión finalizada. Puedes guardar los textos o iniciar otra sesión.")
        if self.closing:
            self.closing = False
            self.close()

    def on_segment(self, segment):
        self.segments.append(segment)
        self.segments.sort(key=lambda s: (s.start, s.id))
        self.dirty = True
        # Rebuild in temporal order even when the two sources finish out of order.
        for editor, field in ((self.original, "original"), (self.translated, "translated")):
            previous_scroll = editor.verticalScrollBar().value()
            at_bottom = editor.verticalScrollBar().value() >= editor.verticalScrollBar().maximum() - 8
            editor.setPlainText("\n\n".join(getattr(s, field) for s in self.segments))
            if at_bottom:
                editor.moveCursor(QTextCursor.MoveOperation.End)
            else:
                editor.verticalScrollBar().setValue(previous_scroll)
        self.subtitle_lines = [s.translated for s in self.segments[-4:]]
        self.subtitle.set_segments(self.segments)

    def on_level(self, source, value):
        (self.system_meter if source == "Sistema" else self.mic_meter).setValue(round(value * 100))

    def on_mode_changed(self, model):
        self.model.setCurrentIndex(self.model.findData(model))
        self.status.setText("Modo Rápido activado para reducir el retraso. Se conserva todo el audio pendiente de procesar.")

    def tick(self):
        now = time.monotonic()
        if self.recording and not self.paused:
            self.elapsed += now - self.last_tick
            self.duration.setText(timestamp(self.elapsed).split(".")[0])
        self.last_tick = now
        # Closing the floating window must also update its checkbox.
        if self.subtitle_positioned and not self.subtitle.isVisible() and self.show_subtitles.isChecked():
            self.show_subtitles.setChecked(False)

    def toggle_subtitles(self, visible):
        if visible:
            if not self.subtitle_positioned:
                screen = self.screen().availableGeometry()
                self.subtitle.move(screen.center().x() - self.subtitle.width() // 2, screen.bottom() - self.subtitle.height() - 35)
                self.subtitle_positioned = True
            self.subtitle.show()
        else:
            self.subtitle.hide()

    def save(self):
        if not self.segments or self.engine is not None:
            return False
        filename = f"Traduccion_{self.created:%Y-%m-%d_%H-%M-%S}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar transcripción y traducción", str(Path.home() / "Documents" / filename), "Texto UTF-8 (*.txt)")
        if not path:
            return False
        if not Path(path).suffix:
            path += ".txt"
        try:
            export_text(Path(path), self.created, self.segments)
        except Exception as exc:
            QMessageBox.warning(self, "No se pudo guardar", f"Revisa la ubicación y el espacio disponible.\n{exc}")
            return False
        self.dirty = False
        self.status.setText(f"Textos guardados en: {path}")
        return True

    def closeEvent(self, event: QCloseEvent):
        if self.engine is not None:
            if not self.closing:
                answer = QMessageBox.question(self, "Sesión activa", "¿Detener la sesión y terminar de traducir antes de cerrar?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer == QMessageBox.StandardButton.Yes:
                    self.closing = True
                    self.stop()
            event.ignore()
            return
        if not self.discard_allowed():
            event.ignore()
            return
        self.subtitle.hide()
        event.accept()

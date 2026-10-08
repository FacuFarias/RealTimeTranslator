import sys
import json
import os
from pathlib import Path

from translator import paths  # Set offline model paths before importing engines.
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTranslator, QLocale, QLibraryInfo, QTimer
from translator.ui import MainWindow


def main():
    if "--self-test" in sys.argv:
        from translator.diagnostics import self_test
        return self_test(sys.argv[1:])
    app = QApplication(sys.argv)
    app.setApplicationName("Traductor local")
    app.setStyle("Fusion")
    app.translator = QTranslator()
    app.translator.load(QLocale("es"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    app.installTranslator(app.translator)
    window = MainWindow()
    window.show()
    startup_test_report = os.environ.get("TRADUCTOR_STARTUP_TEST_REPORT")
    if startup_test_report:
        def finish_startup_test():
            Path(startup_test_report).write_text(json.dumps({"success": window.isVisible(), "executable": sys.executable,
                "window_title": window.windowTitle(), "models_path": str(paths.MODELS), "module_paths": sys.path}, ensure_ascii=False, indent=2), encoding="utf-8")
            window.close()
        QTimer.singleShot(750, finish_startup_test)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

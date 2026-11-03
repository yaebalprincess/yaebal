"""Read shared plain-text news in a worker, including replacements by editors."""
import threading
from pathlib import Path
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QLabel


class NewsSignals(QObject):
    loaded = pyqtSignal(str, str)


class NewsDialog(QDialog):
    def __init__(self, parent, source: Path, prefix: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Новости обновлений")
        self.resize(760, 600)
        self.source, self.prefix, self.loading, self.last_text = source, str(prefix or ""), False, None
        layout = QVBoxLayout(self)
        self.body = QTextBrowser(self)
        self.body.setReadOnly(True)
        layout.addWidget(self.body)
        self.error = QLabel(self)
        self.error.hide()
        layout.addWidget(self.error)
        self.signals = NewsSignals(self)
        self.signals.loaded.connect(self._loaded)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        from .analytics_ui import apply_surface_theme
        apply_surface_theme(self, parent.ui_settings.theme == "dark")
        self.timer.start()
        QTimer.singleShot(0, self.poll)

    def poll(self):
        if self.loading:return
        self.loading = True
        source, signals = self.source, self.signals
        def worker():
            try:
                if source.exists():
                    with source.open("rb") as stream:raw = stream.read(2 * 1024 * 1024 + 1)
                    if len(raw) > 2 * 1024 * 1024:raise ValueError("Файл новостей больше 2 МБ")
                    try:text = raw.decode("utf-8-sig")
                    except UnicodeDecodeError:text = raw.decode("cp1251")
                else:text = ""
                error = ""
            except Exception as exc:text, error = "", str(exc)
            try:signals.loaded.emit(text, error)
            except RuntimeError:pass
        threading.Thread(target=worker, name="SmartOrderNews", daemon=True).start()

    def _loaded(self, text, error):
        self.loading = False
        self.error.setVisible(bool(error))
        self.error.setText("Не удалось прочитать новости: " + error if error else "")
        display = (self.prefix + "\n\n" + text).strip() if self.prefix else text
        if not error and self.last_text != display:
            scroll = self.body.verticalScrollBar().value()
            self.body.setPlainText(display)
            self.body.verticalScrollBar().setValue(scroll)
            self.last_text = display

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

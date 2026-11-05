"""About page using the same glass cards as the rest of the workspace."""
from __future__ import annotations

import platform

from PyQt5.QtCore import Qt, QUrl, QPointF
from PyQt5.QtGui import QDesktopServices, QPainter, QPen, QColor
from PyQt5.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from .config import APP_VERSION
from .heavy_ui import (_RC18SupportDialog,
    ensure_usage_policy_document, ensure_troubleshooting_document, ResponsiveGrid)


class DownloadGuideButton(QToolButton):
    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.setObjectName("DownloadUserGuide")
        self.setFixedSize(34, 34)
        self.setToolTip("Скачать руководство пользователя в PDF")
        self.setAccessibleName("Скачать руководство пользователя в PDF")
        self.clicked.connect(self.download)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#63b4ff" if self.owner.ui_settings.theme == "dark" else "#007aff"), 1.8))
        painter.drawLine(QPointF(17,8),QPointF(17,22))
        painter.drawLine(QPointF(12,17),QPointF(17,22));painter.drawLine(QPointF(22,17),QPointF(17,22))
        painter.drawLine(QPointF(9,22),QPointF(9,27));painter.drawLine(QPointF(9,27),QPointF(25,27));painter.drawLine(QPointF(25,27),QPointF(25,22))

    def download(self):
        from pathlib import Path
        from .user_guide import export_guide_pdf
        default = str(Path.home() / "Downloads" / "Руководство_пользователя_SmartOrder.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить руководство пользователя", default, "PDF (*.pdf)")
        if not path: return
        if not path.lower().endswith(".pdf"): path += ".pdf"
        try:
            export_guide_pdf(path)
            QMessageBox.information(self.owner, "Руководство пользователя", "Руководство сохранено:\n" + path)
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self.owner, "Руководство пользователя", str(exc))


def build_about_page(owner):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    scroll.setWidget(content)
    root = QVBoxLayout(content)
    root.setContentsMargins(22, 20, 22, 16)
    root.setSpacing(16)

    title = QLabel("Smart Order")
    title.setObjectName("TitleLabel")
    title.setAlignment(Qt.AlignCenter)
    title.setTextInteractionFlags(Qt.TextSelectableByMouse)
    root.addWidget(title)
    edition = QLabel("Enterprise Edition")
    edition.setObjectName("SubtitleLabel")
    edition.setAlignment(Qt.AlignCenter)
    root.addWidget(edition)
    tagline = QLabel("Формирование нарядов на работу · Liquid Glass")
    tagline.setAlignment(Qt.AlignCenter)
    tagline.setWordWrap(True)
    tagline.setObjectName("MutedLabel")
    root.addWidget(tagline)
    cards = []

    def card(title, description):
        frame = QFrame()
        frame.setObjectName("LiquidCard")
        box = QVBoxLayout(frame)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        box.addWidget(heading)
        text = QLabel(description)
        text.setWordWrap(True)
        text.setObjectName("MutedLabel")
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(text)
        cards.append(frame)
        return box

    def button(box, title, action, primary=False):
        control = QPushButton(title)
        control.setObjectName("PrimaryButton" if primary else "SecondaryButton")
        control.clicked.connect(action)
        box.addWidget(control)
        return control

    system = card("Система", f"Версия {APP_VERSION} · Python {platform.python_version()}\n"
                  "PyQt5 · Qt Widgets и Chromium\n"
                  "Общая база, история изменений и рабочие пространства цехов.")
    def open_policy():
        path = ensure_usage_policy_document()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    button(system, "Положение об использовании ПО", open_policy)

    docs = card("Документация", "Инструкции по работе с нарядами, справочниками и общими данными.")
    download_row = QHBoxLayout(); download_row.addStretch()
    download_row.addWidget(DownloadGuideButton(owner))
    docs.addLayout(download_row)
    button(docs, "Как работать в программе?", owner._open_guide, True)
    def open_troubleshooting():
        path = ensure_troubleshooting_document()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    button(docs, "Возможные проблемы при работе", open_troubleshooting)
    button(docs, "Новости обновлений", owner.show_news)

    help_box = card("Помощь", "Контакты поддержки и восстановление доступа к программе.")
    button(help_box, "Забыли пароль?", lambda: _RC18SupportDialog("password", owner).exec_())
    button(help_box, "Прочие вопросы", lambda: _RC18SupportDialog("other", owner).exec_())
    for frame in cards:
        frame.layout().addStretch()
    root.addWidget(ResponsiveGrid(cards, min_cell_width=380, max_columns=3))

    footer = QTextBrowser()
    footer.setObjectName("AboutFooter")
    footer.setOpenLinks(False)
    footer.setHtml('<span>Powered by OITS&amp;ZI · Copyright © 2026 </span>'
                   '<a href="https://tmbsir.ru/" style="color:#0785ff;text-decoration:underline">tmbsir</a>')
    footer.setMaximumHeight(56)
    footer.anchorClicked.connect(QDesktopServices.openUrl)
    root.addStretch(1)
    root.addWidget(footer)
    owner.about_session_label = QLabel()
    owner.about_session_label.setObjectName("SessionLabel")
    owner.about_session_label.setAlignment(Qt.AlignRight)
    root.addWidget(owner.about_session_label)
    owner._update_session_labels()
    return scroll

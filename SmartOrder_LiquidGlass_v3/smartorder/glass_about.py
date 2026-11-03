"""About page using the same glass cards as the rest of the workspace."""
from __future__ import annotations

import platform

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QFrame, QLabel, QPushButton,
    QScrollArea, QTextBrowser, QVBoxLayout, QWidget)

from .config import APP_VERSION
from .heavy_ui import (_RC16DownloadBanner, _RC18SupportDialog,
    ensure_usage_policy_document, ensure_troubleshooting_document, ResponsiveGrid)


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
    button(docs, "Как работать в программе?", owner._open_guide, True)
    button(docs, "Скачать руководство в PDF", lambda: owner._rc16_download_guide_pdf(content))
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
    root.addWidget(footer)
    owner.about_session_label = QLabel()
    owner.about_session_label.setObjectName("SessionLabel")
    owner.about_session_label.setAlignment(Qt.AlignRight)
    root.addWidget(owner.about_session_label)
    owner._update_session_labels()
    root.addStretch()
    content._rc16_download_banner = _RC16DownloadBanner(content)
    return scroll

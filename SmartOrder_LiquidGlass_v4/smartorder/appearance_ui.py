"""Administration controls for per-element typography and wallpaper."""
from copy import deepcopy
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFontComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTabWidget, QVBoxLayout, QWidget)

from .appearance import import_wallpaper
from .appearance_config import FONT_ROLES, normalize_appearance


class AppearancePanel(QGroupBox):
    def __init__(self, owner):
        super().__init__("Персонализация")
        self.setObjectName("AppearancePanel")
        self.owner = owner
        self.draft = normalize_appearance(owner.ui_settings.appearance)
        root = QVBoxLayout(self)
        note = QLabel("Шрифты и фон для всех вкладок. Настройки сохраняются на этом компьютере для текущей базы.")
        note.setWordWrap(True)
        root.addWidget(note)
        pages = QTabWidget()
        root.addWidget(pages)
        font_page = QWidget()
        grid = QGridLayout(font_page)
        for col, title in enumerate(["Элемент", "Шрифт", "Размер, пкс", "Жирность", "Курсив", "Образец"]):
            grid.addWidget(QLabel(title), 0, col)
        self.font_controls = {}
        weights = [(100, "Тонкий"), (200, "Сверхлёгкий"), (300, "Лёгкий"), (400, "Обычный"),
                   (500, "Средний"), (600, "Полужирный"), (700, "Жирный"), (800, "Сверхжирный"), (900, "Чёрный")]
        for row, (role, (label, _, _)) in enumerate(FONT_ROLES.items(), 1):
            spec = self.draft["fonts"][role]
            family = QFontComboBox()
            family.setObjectName("FontFamily_" + role)
            family.setFontFilters(QFontComboBox.AllFonts)
            family.setMinimumWidth(160)
            family.setCurrentFont(QFont(spec["family"]))
            size = QDoubleSpinBox()
            size.setObjectName("FontSize_" + role)
            size.setRange(6, 64); size.setSingleStep(.5); size.setDecimals(1); size.setValue(spec["size"])
            weight = QComboBox()
            weight.setObjectName("FontWeight_" + role)
            for value, title in weights: weight.addItem(title, value)
            weight.setCurrentIndex(weight.findData(spec["weight"]))
            italic = QCheckBox()
            italic.setObjectName("FontItalic_" + role)
            italic.setChecked(spec["italic"])
            preview = QLabel("Аа Бб 123")
            preview.setProperty("fontRole", "preview")
            preview.setMinimumWidth(120)
            self.font_controls[role] = (family, size, weight, italic, preview)
            for col, widget in enumerate([QLabel(label), family, size, weight, italic, preview]):
                grid.addWidget(widget, row, col)
            for signal in (family.currentFontChanged, size.valueChanged, weight.currentIndexChanged, italic.toggled):
                signal.connect(lambda *_, key=role: self.update_preview(key))
            self.update_preview(role, preserve_family=True)
        grid.setColumnStretch(1, 1)
        pages.addTab(font_page, "Шрифты")

        background = QWidget()
        box = QVBoxLayout(background)
        self.background_mode = QComboBox()
        self.background_mode.setObjectName("BackgroundMode")
        for title, key in [("Стандартный фон", "builtin"), ("Без фонового изображения", "none"), ("Своё изображение", "custom")]:
            self.background_mode.addItem(title, key)
        self.background_mode.setCurrentIndex(self.background_mode.findData(self.draft["background_mode"]))
        box.addWidget(self.background_mode)
        self.background_name = QLabel()
        self.background_name.setWordWrap(True)
        box.addWidget(self.background_name)
        row = QHBoxLayout()
        self.choose_background = QPushButton("Выбрать изображение…")
        self.choose_background.setObjectName("ChooseBackground")
        self.choose_background.clicked.connect(self.select_background)
        row.addWidget(self.choose_background)
        remove = QPushButton("Убрать своё изображение")
        remove.clicked.connect(self.remove_background)
        row.addWidget(remove)
        row.addStretch()
        box.addLayout(row)
        hint = QLabel("Без изображения останется спокойный однотонный фон. Всплывающие окна размывают содержимое под собой при любом фоне.")
        hint.setWordWrap(True)
        box.addWidget(hint)
        box.addStretch()
        self.background_mode.currentIndexChanged.connect(self.background_changed)
        pages.addTab(background, "Фон")
        self.background_changed()
        footer = QHBoxLayout()
        reset = QPushButton("По умолчанию")
        reset.clicked.connect(self.reset)
        footer.addWidget(reset)
        self.status = QLabel()
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        apply = QPushButton("Применить")
        apply.setObjectName("ApplyAppearance")
        apply.clicked.connect(self.save)
        footer.addWidget(apply)
        root.addLayout(footer)

    def update_preview(self, role, preserve_family=False):
        import json
        family, size, weight, italic, preview = self.font_controls[role]
        if not preserve_family:
            self.draft["fonts"][role]["family"] = family.currentFont().family()
        spec = self.draft["fonts"][role]
        spec.update(size=size.value(), weight=weight.currentData(), italic=italic.isChecked())
        preview.setStyleSheet(f'font-family:{json.dumps(spec["family"])};font-size:{spec["size"]:g}px;'
                             f'font-weight:{spec["weight"]};font-style:{"italic" if spec["italic"] else "normal"};')

    def background_changed(self, *_):
        self.draft["background_mode"] = self.background_mode.currentData()
        self.background_name.setText(Path(self.draft["background_file"]).name if self.draft["background_file"] else "Своё изображение не выбрано")

    def select_background(self):
        path, _ = QFileDialog.getOpenFileName(self, "Фон приложения", "", "Изображения (*.png *.jpg *.jpeg *.bmp *.webp);;Все файлы (*)")
        if not path: return
        try:
            self.draft["background_file"] = str(import_wallpaper(path))
            self.background_mode.setCurrentIndex(self.background_mode.findData("custom"))
            self.background_changed()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Фон приложения", str(exc))

    def remove_background(self):
        self.draft["background_file"] = ""
        self.background_mode.setCurrentIndex(self.background_mode.findData("none"))
        self.background_changed()

    def reset(self):
        defaults = normalize_appearance()
        for role, controls in self.font_controls.items():
            family, size, weight, italic, _ = controls
            spec = defaults["fonts"][role]
            family.setCurrentFont(QFont(spec["family"])); size.setValue(spec["size"])
            weight.setCurrentIndex(weight.findData(spec["weight"])); italic.setChecked(spec["italic"])
        self.draft = deepcopy(defaults)
        for role in self.font_controls: self.update_preview(role, preserve_family=True)
        self.background_mode.setCurrentIndex(0)
        self.background_changed()
        self.status.setText("Настройки по умолчанию подготовлены. Нажмите «Применить».")

    def save(self):
        if self.draft["background_mode"] == "custom" and not self.draft["background_file"]:
            self.status.setText("Сначала выберите изображение.")
            return
        self.owner.set_appearance(normalize_appearance(self.draft))
        self.status.setText("Настройки применены и сохранены.")

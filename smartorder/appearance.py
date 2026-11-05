"""Fonts and locally managed wallpaper shared by all presentation engines."""
import hashlib
import json
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QImageReader
from PyQt5.QtWidgets import QApplication

from .appearance_config import FONT_ROLES, normalize_appearance
from .config import local_state_dir, resource_path

QT_WEIGHTS = {100: 0, 200: 12, 300: 25, 400: 50, 500: 57, 600: 63, 700: 75, 800: 81, 900: 87}


def legacy_surface(widget):
    while widget is not None:
        if widget.property("legacyAppearance") or any(
            cls.__name__ in {"FirstAdminDialog", "HeavyLoginDialog"}
            for cls in type(widget).__mro__
        ):
            return True
        widget = widget.parentWidget()
    return False


def restore_startup_surface(dialog):
    """Keep authentication outside global glass, scaling and font overrides."""
    dialog.setProperty("legacyAppearance", True)
    dialog.setAttribute(Qt.WA_TranslucentBackground, False)
    dialog.setAttribute(Qt.WA_NoSystemBackground, False)
    dialog.setWindowFlag(Qt.FramelessWindowHint, False)
    dialog.setStyleSheet('''
QDialog {background:#f5f5f7;color:#1d1d1f;font:13px "Segoe UI";}
QLabel {background:transparent;color:#1d1d1f;}
QLineEdit {background:#fff;color:#1d1d1f;border:1px solid #b6cadf;
 border-radius:9px;padding:8px 12px;min-height:28px;}
QPushButton {background:#e5effb;color:#007aff;border:1px solid #88b6ed;
 border-radius:9px;padding:8px 14px;min-height:28px;}
QPushButton#PrimaryButton {background:#007aff;color:white;}
''')


def appearance_of(widget=None):
    while widget is not None:
        settings = getattr(widget, "ui_settings", None)
        if settings is not None:
            return normalize_appearance(settings.appearance)
        widget = widget.parentWidget()
    app = QApplication.instance()
    return normalize_appearance(getattr(app, "_liquid_appearance", None))


def font_for(role="body", zoom=100, appearance=None):
    spec = normalize_appearance(appearance)["fonts"].get(role)
    font = QFont(spec["family"])
    font.setPixelSize(max(6, round(spec["size"] * zoom / 100)))
    font.setWeight(QT_WEIGHTS[spec["weight"]])
    font.setItalic(spec["italic"])
    return font


def typography_qss(appearance, zoom):
    normalized = normalize_appearance(appearance)
    rules = []
    for role, spec in normalized["fonts"].items():
        # Quote family names as data. No family can inject a QSS declaration.
        family = json.dumps(spec["family"], ensure_ascii=False)
        scale = 1 if role in {"window_title", "caption"} else zoom / 100
        rules.append(f'QWidget[fontRole="{role}"]{{font-family:{family};'
                     f'font-size:{max(6, spec["size"] * scale):g}px;font-weight:{spec["weight"]};'
                     f'font-style:{"italic" if spec["italic"] else "normal"};}}')
    body = normalized["fonts"]["body"]
    rules.append(f'QWidget[fontRole="subtitle"]{{font-family:{json.dumps(body["family"])};font-size:{body["size"] * zoom / 100:g}px;font-weight:400;font-style:normal;}}')
    return "\n".join(rules)


def wallpaper_path(appearance):
    settings = normalize_appearance(appearance)
    if settings["background_mode"] == "none":
        return None
    if settings["background_mode"] == "custom":
        path = Path(settings["background_file"])
        managed = local_state_dir() / "appearance" / "backgrounds"
        try:
            if path.is_file() and path.resolve().is_relative_to(managed.resolve()):
                return path
        except (OSError, ValueError):
            pass
        return None
    return resource_path("smartorder/glass/assets/factory-glass.png")


def import_wallpaper(path):
    """Decode a selected image, bound its dimensions and copy into local settings."""
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Выберите изображение размером до 32 МБ.")
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > 80_000_000:
        raise ValueError("Изображение слишком большое или его формат не поддерживается.")
    if max(size.width(), size.height()) > 2560:
        size.scale(2560, 2560, Qt.KeepAspectRatio)
        reader.setScaledSize(size)
    image = reader.read()
    if image.isNull():
        raise ValueError("Не удалось открыть изображение: " + reader.errorString())
    folder = local_state_dir() / "appearance" / "backgrounds"
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:24]
    target = folder / (digest + ".png")
    if not image.save(str(target), "PNG"):
        raise OSError("Не удалось сохранить выбранный фон.")
    return target

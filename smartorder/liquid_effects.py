"""Liquid Glass presentation for native Qt pages and every nested dialog.

Effects are painted by mouse-transparent children, never by window opacity or
by graphics effects on editable tables.  A single timer runs only while a
pointer highlight, ripple or transition is moving. No database access here.
"""
from __future__ import annotations

import time
import weakref
import re

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath,
                         QPen, QPixmap, QRadialGradient)
from PyQt5.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication,
    QCalendarWidget, QComboBox, QDialog, QFrame, QGroupBox, QLabel, QLineEdit, QMainWindow,
    QMenu, QPushButton, QScrollArea, QTabBar, QTextBrowser, QToolButton, QWidget)

from .config import resource_path
from .liquid_style import colors
from .appearance import appearance_of, wallpaper_path, legacy_surface
from .live_glass import (LiveGlassBackdrop, attach_overlay, prepare_overlay,
                         update_overlay_geometry)


def theme_of(widget):
    fallback = None
    while widget is not None:
        settings = getattr(widget, "ui_settings", None)
        if settings is not None:
            return settings.theme
        theme = widget.property("theme")
        if fallback is None and theme in ("light", "dark"):
            fallback = theme
        widget = widget.parentWidget()
    app = QApplication.instance()
    return fallback or getattr(app, "_liquid_theme", "light")


class GlassBackdrop(QWidget):
    """Same pre-blurred factory artwork as the Chromium home screen."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("LiquidBackdrop")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self._cache_key = None
        self._cache = QPixmap()
        self.setGeometry(parent.rect())
        self.lower()
        self.show()

    def paintEvent(self, event):
        app = QApplication.instance()
        dark = theme_of(self.parentWidget()) == "dark"
        source_path = wallpaper_path(appearance_of(self.parentWidget()))
        key = (self.size(), self.devicePixelRatioF(), dark, str(source_path))
        if self._cache_key != key:
            cached = getattr(app, "_liquid_wallpaper", (None, QPixmap()))
            if cached[0] != str(source_path):
                cached = (str(source_path), QPixmap(str(source_path)) if source_path else QPixmap())
                app._liquid_wallpaper = cached
            source = cached[1]
            ratio = self.devicePixelRatioF()
            self._cache = QPixmap(round(self.width() * ratio), round(self.height() * ratio))
            self._cache.setDevicePixelRatio(ratio)
            self._cache.fill(QColor(colors(dark)["base"]))
            p = QPainter(self._cache)
            if not source.isNull():
                # Cover/crop is identical to CSS background-size:cover.
                factor = max(self.width() / source.width(), self.height() / source.height())
                w, h = source.width() * factor, source.height() * factor
                p.drawPixmap(QRectF((self.width()-w)/2, (self.height()-h)/2, w, h), source, QRectF(source.rect()))
            tint = QLinearGradient(0, 0, self.width(), self.height())
            tint.setColorAt(0, QColor(15, 30, 51, 218) if dark else QColor(238, 249, 255, 158))
            tint.setColorAt(.48, QColor(18, 41, 66, 210) if dark else QColor(216, 236, 253, 128))
            tint.setColorAt(1, QColor(22, 40, 64, 220) if dark else QColor(231, 243, 255, 146))
            p.fillRect(self.rect(), tint)
            p.end()
            self._cache_key = key
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(172, 210, 248, 90) if dark else QColor(255, 255, 255, 230), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 18, 18)


class ControlLight(QWidget):
    """Cursor-following lens and press wave without stealing input/focus."""
    def __init__(self, target):
        super().__init__(target)
        self.setObjectName("LiquidControlLight")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self.position = QPointF(target.rect().center())
        self.destination = QPointF(self.position)
        self.amount = 0.0
        self.goal = 0.0
        self.ripples = []
        self.setGeometry(target.rect())
        self.hide()

    def tick(self, now):
        target = self.parentWidget()
        if not target.isVisible() or not target.isEnabled():
            self.amount = self.goal = 0
            self.ripples.clear()
            self.hide()
            return False
        self.position += (self.destination - self.position) * .22
        self.amount += (self.goal - self.amount) * .22
        self.ripples = [r for r in self.ripples if now - r[0] < .48]
        moving = abs(self.goal - self.amount) > .006 or (self.destination - self.position).manhattanLength() > .4
        if not moving:
            self.amount = self.goal
            self.position = QPointF(self.destination)
        self.setVisible(self.amount > .006 or bool(self.ripples))
        self.raise_()
        self.update()
        return moving or bool(self.ripples)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.setClipPath(path)
        primary = self.parentWidget().objectName() == "PrimaryButton"
        if self.amount > .005:
            glow = QRadialGradient(self.position, max(70, self.width() * .72))
            glow.setColorAt(0, QColor(255, 255, 255, round((88 if primary else 140) * self.amount)))
            glow.setColorAt(.45, QColor(124, 207, 255, round(48 * self.amount)))
            glow.setColorAt(1, QColor(130, 207, 255, 0))
            p.fillPath(path, glow)
            p.setPen(QPen(QColor(255, 255, 255, round(160 * self.amount)), 1))
            p.drawLine(QPointF(10, 1), QPointF(max(10, self.width()-10), 1))
        now = time.monotonic()
        for started, point in self.ripples:
            t = min(1, (now - started) / .48)
            radius = max(self.width(), self.height()) * (1 - (1-t)**3)
            wave = QRadialGradient(point, max(1, radius))
            wave.setColorAt(0, QColor(255, 255, 255, round(65 * (1-t))))
            wave.setColorAt(.82, QColor(174, 222, 255, round(90 * (1-t))))
            wave.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillPath(path, wave)


class PageTransition(QWidget):
    """Fade a snapshot away; live controls and WebEngine keep their own paint."""
    def __init__(self, target, snapshot=None):
        super().__init__(target)
        self.setObjectName("LiquidPageTransition")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self.snapshot = snapshot
        self.started = time.monotonic()
        self.duration = .22
        self.amount = 1.0
        self.setGeometry(target.rect())
        self.show()
        self.raise_()

    def tick(self, now):
        t = min(1.0, (now-self.started)/self.duration)
        self.amount = (1-t)**3
        self.update()
        if t >= 1:
            self.hide()
            self.deleteLater()
            return False
        return True

    def paintEvent(self, event):
        p = QPainter(self)
        p.setOpacity(self.amount)
        if self.snapshot is not None and not self.snapshot.isNull():
            p.drawPixmap(self.rect(), self.snapshot)
        else:
            p.fillRect(self.rect(), QColor(21, 39, 62) if theme_of(self) == "dark" else QColor(228, 243, 255))


class LiquidController(QObject):
    def __init__(self, app):
        super().__init__(app)
        QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
        self.app = app
        self.lights = weakref.WeakKeyDictionary()
        self.active = weakref.WeakSet()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self._styling = False
        app.installEventFilter(self)

    def wake(self, effect):
        self.active.add(effect)
        if not self.timer.isActive():
            self.timer.start()

    def _tick(self):
        now = time.monotonic()
        for effect in list(self.active):
            if sip.isdeleted(effect) or not effect.tick(now):
                self.active.discard(effect)
        if not self.active:
            self.timer.stop()

    def transition(self, widget, snapshot=None):
        if snapshot is None or snapshot.isNull():
            return
        old = getattr(widget, "_liquid_transition", None)
        if old is not None and not sip.isdeleted(old):
            self.active.discard(old)
            old.hide()
            old.deleteLater()
        effect = PageTransition(widget, snapshot)
        widget._liquid_transition = effect
        self.wake(effect)

    def backdrop(self, root):
        if getattr(root, "_liquid_backdrop", None) is None:
            root._liquid_backdrop = GlassBackdrop(root)
        root._liquid_backdrop.setGeometry(root.rect())
        root._liquid_backdrop.update()

    def style_widget(self, widget, theme):
        if getattr(widget, "_liquid_applied_theme", None) == theme: return
        if isinstance(widget, (GlassBackdrop, LiveGlassBackdrop, ControlLight, PageTransition)) or legacy_surface(widget):
            return
        changed = widget.property("theme") != theme
        if changed and hasattr(widget, "setTheme"):
            widget.setTheme(theme)
        role = widget.property("fontRole")
        if role not in {"preview", "subtitle"} and not widget.property("liquidGlass"):
            from PyQt5.QtWidgets import QAbstractSpinBox, QHeaderView
            chosen = "body"
            if isinstance(widget, QAbstractButton): chosen = "buttons"
            if isinstance(widget, (QLineEdit, QComboBox, QAbstractSpinBox)): chosen = "inputs"
            if isinstance(widget, QAbstractItemView): chosen = "table"
            if isinstance(widget, QHeaderView): chosen = "table_header"
            if isinstance(widget, QTabBar): chosen = "tabs"
            if widget.objectName() in {"TitleLabel", "SectionTitle"}: chosen = "heading"
            if role == "heading" or (isinstance(widget, QLabel) and re.search(r"font-size:\s*(?:1[7-9]|[2-9][0-9])(?:px|pt)",widget.styleSheet())): chosen = "heading"
            if widget.objectName() in {"WindowTitleLabel", "OverlayTitle"}: chosen = "window_title"
            if widget.objectName() in {"TitleThemeCaption", "UserWorkshopBadge", "NotificationBell"}: chosen = "caption"
            if widget.parentWidget() is not None and widget.parentWidget().objectName() == "UnifiedScaleToolbar": chosen = "caption"
            changed = changed or role != chosen
            widget.setProperty("fontRole", chosen)
            if widget.styleSheet():
                css = re.sub(r"font-(?:family|size|weight|style)\s*:[^;}]+;?", "", widget.styleSheet(), flags=re.I)
                if css != widget.styleSheet(): widget.setStyleSheet(css)
        widget.setProperty("theme", theme)
        widget.setProperty("liquidGlass", True)
        icon_name = widget.property("symbolIcon")
        if icon_name and hasattr(widget, "setIcon"):
            from .symbols import symbol_icon
            widget.setIcon(symbol_icon(icon_name, theme))
        if widget.objectName() == "GlassOverlayChrome":
            widget.dark = theme == "dark"
        if isinstance(widget, QAbstractItemView):
            widget.setMouseTracking(True)
            widget.viewport().setMouseTracking(True)
        if isinstance(widget, (QAbstractButton, QLineEdit, QComboBox)):
            widget.setMouseTracking(True)
        # Old local styles bypass QApplication QSS. Retire only the visual
        # overrides on standard controls; calculated cell brushes stay intact.
        if isinstance(widget, (QPushButton, QToolButton, QLineEdit, QComboBox, QMenu)) and widget.styleSheet():
            if widget.objectName() not in {"ScrollTopButton"} and widget.__class__.__name__ != "_RC16GlyphButton":
                layout_style = ""
                if isinstance(widget, QComboBox) and hasattr(widget, "_arrow_rect"):
                    layout_style = "QComboBox{padding-right:62px;}QComboBox::drop-down{width:0;border:none;}QComboBox::down-arrow{image:none;width:0;height:0;}"
                if widget.styleSheet() != layout_style:
                    widget.setStyleSheet(layout_style)
        if isinstance(widget, QCalendarWidget) and widget.styleSheet():
            widget.setStyleSheet("")
        if isinstance(widget, QScrollArea):
            widget.setAutoFillBackground(False)
            widget.viewport().setAutoFillBackground(False)
        if widget.objectName() == "qt_scrollarea_viewport":
            widget.setAutoFillBackground(False)
        if changed:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

        widget._liquid_applied_theme = theme

    def apply(self, root, theme=None):
        if self._styling or sip.isdeleted(root) or legacy_surface(root):
            return
        self._styling = True
        try:
            theme = theme or theme_of(root)
            if (isinstance(root, QDialog) or root.objectName() == "NotificationPopup") and root.styleSheet() and root.styleSheet() != getattr(root,"_liquid_scoped_qss",None):
                root.setStyleSheet("")
            self.style_widget(root, theme)
            visible_only = isinstance(root, QMainWindow) and root.isVisible()
            for child in root.findChildren(QWidget):
                if visible_only and not child.isVisible():
                    continue
                self.style_widget(child, theme)
            if self.is_overlay(root):
                attach_overlay(root)
            elif root.objectName() == "LiquidNativeShell":
                self.backdrop(root)
            elif isinstance(root, QMainWindow) and root.centralWidget() is not None:
                self.backdrop(root.centralWidget())
            for child in root.findChildren(GlassBackdrop):
                child.update()
        finally:
            self._styling = False

    @staticmethod
    def is_overlay(widget):
        # Qt creates private combo popup windows during polish. Converting those
        # hidden native containers to glass surfaces can expose empty windows.
        return not widget.property("plainSurface") and (isinstance(widget, (QDialog, QMenu)) or bool(widget.property("liquidPopup"))
                or widget.objectName() in {"NotificationPopup", "RC5InfoPopup"})

    def eventFilter(self, widget, event):
        if not isinstance(widget, QWidget) or isinstance(widget, (GlassBackdrop, LiveGlassBackdrop, ControlLight, PageTransition)) or legacy_surface(widget):
            return False
        kind = event.type()
        if widget.property("plainSurface") or widget.window().property("plainSurface"):return False
        overlay = self.is_overlay(widget)
        if kind == QEvent.Polish and overlay:
            prepare_overlay(widget)
        if kind == QEvent.Show:
            from .i18n import apply_widget, apply_language
            apply_language(widget) if overlay else apply_widget(widget)
            if overlay:
                self.apply(widget)
            else:
                self.style_widget(widget, theme_of(widget))
        elif kind == QEvent.Hide:
            backdrop = getattr(widget, "_liquid_backdrop", None)
            if isinstance(backdrop, LiveGlassBackdrop): backdrop.stop()
        elif kind in (QEvent.Move, QEvent.WindowStateChange):
            backdrop = getattr(widget, "_liquid_backdrop", None)
            if isinstance(backdrop, LiveGlassBackdrop):
                backdrop.moved() if kind == QEvent.Move else backdrop.schedule()
                if kind == QEvent.WindowStateChange: update_overlay_geometry(widget)
        elif kind == QEvent.Paint and isinstance(widget, QMenu):
            backdrop = getattr(widget, "_liquid_backdrop", None)
            if isinstance(backdrop, LiveGlassBackdrop):
                painter = QPainter(widget); backdrop.paint_to(painter); painter.end()
        elif kind == QEvent.Resize:
            backdrop = getattr(widget, "_liquid_backdrop", None)
            if backdrop is not None:
                backdrop.setGeometry(widget.rect())
                if isinstance(backdrop, LiveGlassBackdrop):
                    update_overlay_geometry(widget);backdrop.schedule()
            transition = getattr(widget, "_liquid_transition", None)
            if transition is not None and not sip.isdeleted(transition):
                transition.setGeometry(widget.rect())
            light = self.lights.get(widget)
            if light is not None:
                light.setGeometry(widget.rect())
        elif kind == QEvent.DynamicPropertyChange and event.propertyName() == b"theme":
            backdrop = getattr(widget, "_liquid_backdrop", None)
            if backdrop is not None:
                backdrop.update()
        if isinstance(widget, QAbstractButton) and not isinstance(widget, QTabBar):
            if not widget.isEnabled() or widget.objectName() in {"WindowControl", "WindowClose"}:
                return False
            if kind in (QEvent.Enter, QEvent.Leave, QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.KeyPress):
                light = self.lights.get(widget)
                if light is None:
                    light = ControlLight(widget)
                    self.lights[widget] = light
                if kind in (QEvent.Enter, QEvent.MouseMove):
                    light.goal = 1
                    if hasattr(event, "pos"):
                        light.destination = QPointF(event.pos())
                elif kind == QEvent.Leave:
                    light.goal = 0
                elif kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    light.ripples.append((time.monotonic(), QPointF(event.pos())))
                elif kind == QEvent.KeyPress and not event.isAutoRepeat() and event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
                    light.ripples.append((time.monotonic(), QPointF(widget.rect().center())))
                self.wake(light)
        return False


def install_liquid_effects(app=None):
    app = app or QApplication.instance()
    if app is None:
        return None
    controller = getattr(app, "_smartorder_liquid", None)
    if controller is None:
        controller = LiquidController(app)
        app._smartorder_liquid = controller
    return controller


def apply_liquid_surface(widget, theme=None):
    controller = install_liquid_effects()
    if controller is not None:
        controller.apply(widget, theme)


def transition_to(widget, snapshot=None):
    controller = install_liquid_effects()
    if controller is not None:
        controller.transition(widget, snapshot)


def style_popup(widget, theme):
    """Theme custom/native combo frames after Qt creates their separate window."""
    controller = install_liquid_effects()
    c = colors(theme == "dark")
    widget.setProperty("liquidPopup", True)
    widget.setStyleSheet(f'''
QFrame[liquidPopup="true"]{{background:{c['glass']};border:1px solid {c['edge']};border-radius:12px;}}
QAbstractItemView{{background:{c['table']};color:{c['ink']};border:none;outline:0;padding:4px;}}
QAbstractItemView::item{{min-height:28px;padding:5px 8px;border-radius:6px;}}
QAbstractItemView::item:selected{{background:{c['selected']};color:{c['ink']};}}
QAbstractItemView::item:hover{{background:{c['hover']};}}
''')
    controller.apply(widget, theme)
    attach_overlay(widget)

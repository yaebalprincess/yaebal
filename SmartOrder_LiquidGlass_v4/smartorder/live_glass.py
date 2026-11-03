"""Rounded translucent overlays sampling the live application beneath them.

Only pixels of the owning application window are sampled. A background-only
blur and a small lens displacement leave dialog text and controls sharp.
No desktop capture, web server or change to the business event handlers.
"""
from __future__ import annotations

import weakref
import time

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PyQt5.QtWidgets import (QApplication, QDialog, QFrame, QGraphicsBlurEffect,
    QGraphicsScene, QHBoxLayout, QLabel, QMenu, QSizeGrip, QToolButton, QWidget)


class GlassTitleBar(QFrame):
    def __init__(self, window):
        super().__init__(window)
        self.window_ref = weakref.ref(window)
        self.drag = None
        self.setObjectName("GlassOverlayChrome")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 3, 6, 3)
        self.title = QLabel(window.windowTitle())
        self.title.setObjectName("OverlayTitle")
        row.addWidget(self.title, 1)
        close = QToolButton()
        close.setText("×"); close.setAccessibleName("Закрыть окно"); close.setToolTip("Закрыть")
        close.setObjectName("OverlayClose")
        close.setFixedSize(30, 28)
        close.clicked.connect(window.close)
        row.addWidget(close)
        window.windowTitleChanged.connect(self.title.setText)

    def mousePressEvent(self, event):
        window = self.window_ref()
        if event.button() == Qt.LeftButton and window is not None:
            handle = window.windowHandle()
            if handle is not None and handle.startSystemMove(): return
            self.drag = event.globalPos() - window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        window = self.window_ref()
        if self.drag is not None and window is not None and event.buttons() & Qt.LeftButton:
            if not window.isMaximized(): window.move(event.globalPos() - self.drag)

    def mouseReleaseEvent(self, event):
        self.drag = None

    def mouseDoubleClickEvent(self, event):
        window = self.window_ref()
        if window is not None and event.button() == Qt.LeftButton:
            window.showNormal() if window.isMaximized() else window.showMaximized()


class LiveGlassBackdrop(QWidget):
    PAD = 30

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("LiveGlassBackdrop")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self.raw = QPixmap()
        self.blurred = QPixmap()
        self._previous = None
        self._refreshing = False
        self._last_move_frame = 0.0
        self.capture_count = 0
        self.source_rect = QRect()
        self.scene = QGraphicsScene(self)
        self.scene.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.item = self.scene.addPixmap(QPixmap())
        self.blur = QGraphicsBlurEffect()
        self.blur.setBlurRadius(18)
        self.blur.setBlurHints(QGraphicsBlurEffect.PerformanceHint)
        self.item.setGraphicsEffect(self.blur)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.refresh)
        self.pending = QTimer(self)
        self.pending.setSingleShot(True); self.pending.setInterval(16)
        self.pending.timeout.connect(self.refresh)
        self.setGeometry(parent.rect())
        self.lower()
        if not isinstance(parent, QMenu): self.show()

    def source(self):
        parent = self.parentWidget().parentWidget()
        return parent.window() if parent is not None else None

    def start(self):
        self.timer.setInterval(250 if self.parentWidget().isMaximized() else 80)
        self.refresh()
        self.timer.start()

    def stop(self):
        self.timer.stop(); self.pending.stop()
        self.raw = QPixmap(); self.blurred = QPixmap(); self._previous = None
        self.item.setPixmap(QPixmap())

    def schedule(self):
        if not self.pending.isActive(): self.pending.start()

    def moved(self):
        # Windows may run a native move loop. Update on the move message too,
        # rather than relying solely on queued Qt timers during a drag.
        now = time.monotonic()
        if now-self._last_move_frame >= 1/30:
            self._last_move_frame = now
            self.refresh()
            self.repaint()
        else:
            self.schedule()

    def refresh(self):
        target = self.parentWidget()
        source = self.source()
        if self._refreshing or not target.isVisible() or source is None or sip.isdeleted(source): return
        if source.isMinimized() or not source.isVisible(): return
        app = QApplication.instance()
        if getattr(app, "_live_glass_capturing", False): return
        self._refreshing = True
        app._live_glass_capturing = True
        try:
            origin = source.mapFromGlobal(target.mapToGlobal(QPoint(0, 0)))
            region = QRect(origin.x()-self.PAD, origin.y()-self.PAD,
                           target.width()+2*self.PAD, target.height()+2*self.PAD)
            self.source_rect = region
            intersection = region.intersected(source.rect())
            ratio = source.devicePixelRatioF()
            raw = QPixmap(round(region.width()*ratio), round(region.height()*ratio))
            raw.setDevicePixelRatio(ratio)
            raw.fill(Qt.transparent)
            if not intersection.isEmpty():
                capture = source.grab(intersection)
                painter = QPainter(raw)
                painter.drawPixmap(QRectF(intersection.translated(-region.topLeft())), capture, QRectF(capture.rect()))
                painter.end()
            image = raw.toImage()
            self.capture_count += 1
            if self._previous is not None and image == self._previous: return
            self._previous = image
            self.raw = raw
            self.item.setPixmap(raw)
            logical = QRectF(0, 0, region.width(), region.height())
            self.scene.setSceneRect(logical)
            blurred = QPixmap(raw.size()); blurred.setDevicePixelRatio(ratio); blurred.fill(Qt.transparent)
            painter = QPainter(blurred)
            self.scene.render(painter, logical, logical)
            painter.end()
            self.blurred = blurred
            self.update()
            if isinstance(target, QMenu): target.update()
        finally:
            self._refreshing = False
            app._live_glass_capturing = False

    def paint_to(self, painter):
        from .liquid_effects import theme_of
        target = self.parentWidget()
        dark = theme_of(target) == "dark"
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(target.rect()).adjusted(.5, .5, -.5, -.5)
        radius = 0 if target.isMaximized() or target.isFullScreen() else 20
        path = QPainterPath(); path.addRoundedRect(r, radius, radius)
        painter.setClipPath(path)
        if not self.blurred.isNull():
            painter.setOpacity(.86 if dark else .82)
            # A shallow lens magnifies the application below the entire panel.
            ratio = self.blurred.devicePixelRatioF()
            inset_x, inset_y = target.width()*.012, target.height()*.012
            sample = QRectF((self.PAD+inset_x)*ratio, (self.PAD+inset_y)*ratio,
                            (target.width()-2*inset_x)*ratio, (target.height()-2*inset_y)*ratio)
            painter.drawPixmap(QRectF(target.rect()), self.blurred, sample)
            # Curved edge bands use a sharper, displaced sample for refraction.
            rim = min(16, target.width()//4, target.height()//4)
            for n in range(rim):
                bend = 4 * (1-n/max(1,rim))**2
                painter.setOpacity(.24*(1-n/max(1,rim)))
                for y in (n, target.height()-n-1):
                    src = QRectF((self.PAD+bend)*ratio, (self.PAD+y+bend*.2)*ratio,
                                 (target.width()-2*bend)*ratio, ratio*1.2)
                    painter.drawPixmap(QRectF(0,y,target.width(),1.2), self.raw, src)
                for x in (n, target.width()-n-1):
                    src = QRectF((self.PAD+x+bend*.2)*ratio, (self.PAD+bend)*ratio,
                                 ratio*1.2, (target.height()-2*bend)*ratio)
                    painter.drawPixmap(QRectF(x,0,1.2,target.height()), self.raw, src)
        painter.setOpacity(1)
        tint = QLinearGradient(r.topLeft(), r.bottomRight())
        tint.setColorAt(0, QColor(16,33,54,138) if dark else QColor(246,252,255,112))
        tint.setColorAt(1, QColor(25,47,73,124) if dark else QColor(218,239,255,92))
        painter.fillPath(path, tint)
        edge = QLinearGradient(r.topLeft(), r.bottomRight())
        edge.setColorAt(0, QColor(255,255,255,220)); edge.setColorAt(.5,QColor(166,213,255,70));edge.setColorAt(1,QColor(255,255,255,160))
        painter.setPen(QPen(QBrush(edge),1));painter.setBrush(Qt.NoBrush);painter.drawPath(path)
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.paint_to(painter)


def prepare_overlay(widget):
    """Run before the native handle is shown so alpha works on Windows."""
    if widget.property("glassOverlay"): return
    widget.setProperty("glassOverlay", True)
    if not widget.isVisible():
        widget.setWindowFlag(Qt.FramelessWindowHint, True)
        widget.setAttribute(Qt.WA_TranslucentBackground, True)
    widget.setAttribute(Qt.WA_NoSystemBackground, True)
    widget.setAutoFillBackground(False)


def attach_overlay(widget):
    prepare_overlay(widget)
    layer = getattr(widget, "_liquid_backdrop", None)
    if not isinstance(layer, LiveGlassBackdrop):
        if layer is not None:
            layer.hide();layer.deleteLater()
        layer = LiveGlassBackdrop(widget)
        widget._liquid_backdrop = layer
    if isinstance(widget, QDialog) and getattr(widget, "_glass_chrome", None) is None:
        layout = widget.layout()
        if layout is not None:
            margins = layout.contentsMargins()
            widget._glass_content_margins = (margins.left(),margins.top(),margins.right(),margins.bottom())
            chrome = GlassTitleBar(widget)
            widget._glass_chrome = chrome
            chrome.show()
            if widget.minimumSize() != widget.maximumSize():
                widget._glass_grip = QSizeGrip(widget)
                widget._glass_grip.show()
    update_overlay_geometry(widget)
    layer.start()
    return layer


def update_overlay_geometry(widget):
    layer = getattr(widget, "_liquid_backdrop", None)
    if layer is not None: layer.setGeometry(widget.rect())
    radius = 0 if widget.isMaximized() or widget.isFullScreen() else 20
    if radius:
        path = QPainterPath();path.addRoundedRect(QRectF(widget.rect()),radius,radius)
        widget.setMask(QRegion(path.toFillPolygon().toPolygon()))
    else: widget.clearMask()
    chrome = getattr(widget, "_glass_chrome", None)
    if chrome is not None:
        from .appearance import appearance_of
        chrome_height = max(36, round(appearance_of(widget)["fonts"]["window_title"]["size"])+12)
        if widget.layout() is not None:
            left, top, right, bottom = widget._glass_content_margins
            widget.layout().setContentsMargins(max(12,left), top+chrome_height+4, max(12,right), max(12,bottom))
        chrome.setGeometry(5,3,max(0,widget.width()-10),chrome_height);chrome.raise_()
    grip = getattr(widget, "_glass_grip", None)
    if grip is not None:
        grip.move(widget.width()-20,widget.height()-20)
        grip.setVisible(not widget.isMaximized())

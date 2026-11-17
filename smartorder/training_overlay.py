"""Frosted training surfaces with a separate, compositor-safe web spotlight."""
import json

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PyQt5.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from .help_surface import tutorial_style


def blurred_frame(frame):
    if frame.isNull():
        return QPixmap()
    ratio = frame.devicePixelRatioF()
    image = frame.toImage()
    small = image.scaled(max(1, image.width()//14), max(1, image.height()//14),
                         Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    result = QPixmap.fromImage(small.scaled(image.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    result.setDevicePixelRatio(ratio)
    return result


def paint_glass(painter, rect, dark, sample=None, source=None, radius=16):
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath(); path.addRoundedRect(QRectF(rect).adjusted(.5, .5, -.5, -.5), radius, radius)
    painter.save(); painter.setClipPath(path)
    painter.fillPath(path, QColor("#192e46" if dark else "#eef7ff"))
    if sample is not None and not sample.isNull():
        painter.drawPixmap(QRectF(rect), sample, QRectF(source or sample.rect()))
    gradient = QLinearGradient(QRectF(rect).topLeft(), QRectF(rect).bottomRight())
    gradient.setColorAt(0, QColor(24, 47, 72, 238) if dark else QColor(246, 252, 255, 238))
    gradient.setColorAt(1, QColor(30, 57, 82, 226) if dark else QColor(219, 239, 255, 225))
    painter.fillPath(path, gradient)
    painter.setPen(QPen(QColor(188, 223, 255, 155) if dark else QColor(255, 255, 255, 245), 1))
    painter.drawPath(path); painter.restore()


class TutorialDialog(QDialog):
    """Glass painted onto an opaque window: text never inherits alpha."""
    def __init__(self, owner):
        super().__init__(owner)
        self.dark = owner.ui_settings.theme == "dark"
        tutorial_style(self, owner.ui_settings.theme)
        backdrop=getattr(getattr(owner,"_legacy_shell",None),"_liquid_backdrop",None)
        self.sample = blurred_frame(backdrop.frame() if backdrop is not None else owner.grab())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#192e46" if self.dark else "#eef7ff"))
        paint_glass(painter, self.rect(), self.dark, self.sample)


class TrainingCard(QFrame):
    def __init__(self, coach, title, text, number, total, informational, confirm):
        super().__init__(coach)
        self.coach = coach
        self.setObjectName("TrainingCard")
        tutorial_style(self, coach.tour.owner.ui_settings.theme)
        self.setAutoFillBackground(False)
        self.setStyleSheet(self.styleSheet()+"QFrame#TrainingCard{background:transparent;border:0;}")
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(14)
        self.scroll = QScrollArea(self); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.content = QWidget(); self.content.setProperty("plainSurface", True)
        body_layout = QVBoxLayout(self.content); body_layout.setContentsMargins(0, 0, 6, 0); body_layout.setSpacing(12)
        self.tag = QLabel(f"ШАГ {number} ИЗ {total} · ОБУЧЕНИЕ МАСТЕРА"); self.tag.setObjectName("TrainingKicker")
        self.heading = QLabel(title); self.heading.setObjectName("TrainingTitle")
        self.body = QLabel(text)
        for label in (self.tag, self.heading, self.body):
            label.setWordWrap(True); body_layout.addWidget(label)
        self.scroll.setWidget(self.content); layout.addWidget(self.scroll, 1)
        self.actions = QHBoxLayout(); self.actions.setSpacing(12)
        self.stop = QPushButton("Завершить обучение", self); self.stop.clicked.connect(coach.tour.request_finish)
        self.actions.addWidget(self.stop); self.actions.addStretch()
        self.confirm = None
        if informational or confirm:
            self.confirm = QPushButton("ОК" if confirm else "Далее", self)
            self.confirm.setObjectName("PrimaryButton")
            self.confirm.clicked.connect(coach.tour.confirm_value if confirm else coach.tour.next)
            self.actions.addWidget(self.confirm)
        layout.addLayout(self.actions)

    def fit(self, width, max_height):
        # QLabel sizeHint() alone does not recompute a wrapped label after a
        # width change. Compute every height at its final available width.
        width = max(240, width)
        self.setFixedWidth(width)
        inner = max(100, width-52)
        body_layout = self.content.layout()
        for label in (self.tag, self.heading, self.body):
            label.setMinimumWidth(0); label.setMaximumWidth(inner)
            label.setFixedHeight(max(label.fontMetrics().height(), label.heightForWidth(inner)))
        natural = sum(label.height() for label in (self.tag, self.heading, self.body)) + 24
        self.content.setMinimumHeight(natural)
        button_height = max(button.sizeHint().height() for button in self.findChildren(QPushButton))
        self.setFixedHeight(min(max_height, natural+button_height+50))
        self.scroll.setMinimumHeight(36)
        self.layout().activate()

    def paintEvent(self, event):
        painter = QPainter(self)
        frame = self.coach.background
        ratio = frame.devicePixelRatioF()
        source = QRectF(self.x()*ratio, self.y()*ratio, self.width()*ratio, self.height()*ratio)
        paint_glass(painter, self.rect(), self.coach.dark, frame, source)


class CoachOverlay(QFrame):
    def __init__(self, tour, host, title, text, number, total, informational=False, confirm=False):
        super().__init__(host)
        self.tour, self.host, self.target = tour, host, QRect()
        self.title, self.text, self.number, self.total = title, text, number, total
        self.dark = tour.owner.ui_settings.theme == "dark"
        self.phase = 0.0; self.extra_holes = []; self.active = True
        self.web = bool(host is tour.owner and getattr(host, "_glass_painted", False)
                        and host.tabs.currentIndex() == 0)
        self.setProperty("plainSurface", True)
        self.setObjectName("ClickTrainingOverlay")
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("QFrame#ClickTrainingOverlay{background:transparent;border:0;}")
        self.setGeometry(self.host_bounds())
        self.background = QPixmap() if self.web else blurred_frame(host.grab())
        self.card = TrainingCard(self, title, text, number, total, informational, confirm)
        self.card.hide()
        self.animation = QVariantAnimation(self); self.animation.setDuration(1800)
        self.animation.setStartValue(0.0); self.animation.setEndValue(1.0); self.animation.setLoopCount(-1)
        self.animation.valueChanged.connect(self._pulse)
        host.installEventFilter(self)
        self.show(); self.raise_(); self.animation.start()

    def _pulse(self, value):
        self.phase = float(value); self.update()

    def web_config(self, passive=False):
        targets = {"create":"#create", "edit":"#edit", "history":"#history-panel"}
        web=self.web_rect()
        return {"title":self.title, "text":self.text, "number":self.number,
                "total":self.total, "target":targets.get(self.tour.key, ""),
                "external":self.tour.key=="administration",
                "anchor":[self.target.x()-web.x(),0,self.target.width(),0],
                "action":self.tour.key, "row":self.tour.key=="edit", "passive":passive}

    def publish_web(self, passive=False):
        if self.web and not sip.isdeleted(self.tour.owner._glass):
            encoded = json.dumps(self.web_config(passive), ensure_ascii=False)
            self.tour.owner._glass.page().runJavaScript("window.SmartOrderCoach&&window.SmartOrderCoach.show("+encoded+")")

    def web_rect(self):
        view = self.tour.owner._glass
        return QRect(view.mapTo(self.host, QPoint()), view.size())

    def host_bounds(self):
        # A QWidget over the WebEngine rectangle can occlude Chromium's
        # compositor even with a hole in its mask. Keep native shading strictly
        # above the view; the DOM owns every pixel inside the web rectangle.
        if self.web:
            return QRect(0,0,self.host.width(),max(1,self.web_rect().top()))
        return self.host.rect()

    def apply_mask(self):
        mask = QRegion(self.rect())
        holes = ([self.web_rect(),self.target] if self.web else [self.target, *self.extra_holes])
        for hole in holes:
            if not hole.isEmpty(): mask = mask.subtracted(QRegion(hole))
        if not self.web and self.active:
            mask = mask.united(QRegion(self.card.geometry()))
        self.setMask(mask)

    def highlight(self, rect):
        self.target = rect.intersected(self.host.rect() if self.web else self.rect())
        if self.web:
            self.card.hide(); self.publish_web(); self.apply_mask(); return
        width = min(480, self.width()-32)
        self.card.fit(width, max(160, self.height()-32))
        height = self.card.height()
        candidates = [QPoint(self.target.left(), self.target.bottom()+18),
                      QPoint(self.target.right()+18, self.target.top()),
                      QPoint(self.target.left(), self.target.top()-height-18),
                      QPoint(self.target.left()-width-18, self.target.top())]
        def fit(point):
            return QPoint(max(16, min(point.x(), self.width()-width-16)),
                          max(16, min(point.y(), self.height()-height-16)))
        def overlap(point):
            r = self.target.intersected(QRect(point, self.card.size()))
            return r.width()*r.height()
        best = min((fit(p) for p in candidates), key=overlap)
        self.card.move(best); self.card.show(); self.card.raise_()
        self.apply_mask(); self.update()

    def passive(self):
        self.active = False; self.target = QRect(); self.extra_holes = []
        self.card.hide(); self.animation.stop(); self.publish_web(True)
        self.apply_mask(); self.raise_(); self.update()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Move):
            self.setGeometry(self.host_bounds())
            if self.active:QTimer.singleShot(0, self.tour.position_target)
            else:self.apply_mask();self.update()
        return False

    def hideEvent(self, event):
        self.animation.stop(); super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        shade = QPainterPath(); shade.setFillRule(Qt.OddEvenFill); shade.addRect(QRectF(self.rect()))
        for hole in [self.target, *self.extra_holes]:
            if not hole.isEmpty(): shade.addRect(QRectF(hole))
        painter.save(); painter.setClipPath(shade)
        if not self.background.isNull(): painter.drawPixmap(self.rect(), self.background)
        painter.fillRect(self.rect(), QColor(5, 17, 32, 163 if self.dark else 145))
        painter.restore()
        if self.target.isEmpty() or not self.active or self.web and self.web_rect().contains(self.target): return
        painter.setPen(QPen(QColor("#62bcff"), 2))
        painter.drawRoundedRect(QRectF(self.target.adjusted(-3, -3, 3, 3)), 10, 10)
        center = QPoint(max(24, min(self.target.left()+10, self.width()-25)), max(26, self.target.top()-13))
        painter.setBrush(Qt.NoBrush)
        for offset in (0.0, .5):
            phase = (self.phase+offset)%1
            painter.setPen(QPen(QColor(74, 177, 255, int(130*(1-phase))), 2))
            radius = 17+phase*18
            painter.drawEllipse(QRectF(center.x()-radius, center.y()-radius, 2*radius, 2*radius))
        painter.setPen(QPen(QColor("#b5e3ff"), 1.5)); painter.setBrush(QColor("#087bfa"))
        painter.drawEllipse(center, 16, 16)
        font = painter.font(); font.setPixelSize(16); font.setBold(True)
        painter.setFont(font); painter.setPen(Qt.white)
        painter.drawText(QRect(center.x()-16, center.y()-16, 32, 32), Qt.AlignCenter, str(self.number))

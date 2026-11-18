"""Frosted training surfaces with a separate, compositor-safe web spotlight."""
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PyQt5.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from .help_surface import tutorial_style


def blurred_frame(frame, scale=14):
    if frame.isNull():
        return QPixmap()
    ratio = frame.devicePixelRatioF()
    image = frame.toImage()
    small = image.scaled(max(1, image.width()//scale), max(1, image.height()//scale),
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
        self.anchor = QRect()
        self.cell_holes = []
        self.web = bool(host is tour.owner and getattr(host, "_glass", None) is not None
                        and not host._glass_error and host.tabs.currentIndex() == 0)
        self.setProperty("plainSurface", True)
        self.setObjectName("ClickTrainingOverlay")
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("QFrame#ClickTrainingOverlay{background:transparent;border:0;}")
        self.gutters = []
        if self.web:
            # Three thin siblings shade the native margins without crossing
            # the web view or occluding its compositor.
            for _ in range(3):
                gutter = QWidget(host)
                gutter.setProperty("plainSurface", True)
                gutter.setAttribute(Qt.WA_TransparentForMouseEvents)
                gutter.setStyleSheet("background:rgba(5,17,32,%d);" % (163 if self.dark else 145))
                self.gutters.append(gutter)
                self.destroyed.connect(gutter.deleteLater)
            host._glass.installEventFilter(self)
        self.setGeometry(self.host_bounds())
        self.place_gutters()
        self.background = QPixmap() if self.web else blurred_frame(host.grab(), scale=7)
        self._sampling = False
        self._sample_geometry = None
        self.sample_timer = QTimer(self)
        self.sample_timer.setSingleShot(True)
        self.sample_timer.setInterval(32)
        self.sample_timer.timeout.connect(self.resample)
        self.card = TrainingCard(self, title, text, number, total, informational, confirm)
        self.card.hide()
        self.shade = QPainterPath()
        self.shade.addRect(QRectF(self.rect()))
        self.animation = QVariantAnimation(self); self.animation.setDuration(1800)
        self.animation.setStartValue(0.0); self.animation.setEndValue(1.0); self.animation.setLoopCount(-1)
        self.animation.valueChanged.connect(self._pulse)
        host.installEventFilter(self)
        self.show(); self.raise_()

    def resample(self):
        if self.web or not self.isVisible():
            return
        # Render the now-settled layout without including the coach itself.
        # Restore the card in the same event turn, before any on-screen paint.
        self._sampling = True
        visible = self.card.isVisible()
        focused = self.window().focusWidget()
        if focused is not None and not self.card.isAncestorOf(focused):
            focused = None
        try:
            if visible:
                self.card.hide()
            self.background = blurred_frame(self.host.grab(), scale=7)
        finally:
            self._sampling = False
            if visible:
                self.card.show()
                if focused is not None and not sip.isdeleted(focused):
                    focused.setFocus(Qt.OtherFocusReason)
            self.update()

    def _pulse(self, value):
        self.phase = float(value)
        center = self.badge_center()
        self.update(QRect(center.x()-38, center.y()-38, 76, 76))

    def web_config(self):
        targets = {"create":"#create", "edit":"#edit", "history":"#history-panel"}
        web=self.web_rect()
        return {"title":self.title, "text":self.text, "number":self.number,
                "total":self.total, "target":targets.get(self.tour.key, ""),
                "external":self.tour.key=="administration",
                "anchor":[self.target.x()-web.x(),0,self.target.width(),0],
                "action":self.tour.key, "row":self.tour.key=="edit", "passive":not self.active}

    def web_rect(self):
        view = self.tour.owner._glass
        return QRect(view.mapTo(self.host, QPoint()), view.size())

    def place_gutters(self):
        if not self.gutters:
            return
        web = self.web_rect()
        width, height = self.host.width(), self.host.height()
        rects = (QRect(0, web.top(), web.left(), web.height()),
                 QRect(web.right()+1, web.top(), width-web.right()-1, web.height()),
                 QRect(0, web.bottom()+1, width, height-web.bottom()-1))
        for gutter, rect in zip(self.gutters, rects):
            gutter.setGeometry(rect)
            gutter.setVisible(not rect.isEmpty())
            gutter.raise_()

    def host_bounds(self):
        # A QWidget over the WebEngine rectangle can occlude Chromium's
        # compositor even with a hole in its mask. Keep native shading strictly
        # above the view; the DOM owns every pixel inside the web rectangle.
        if self.web:
            return QRect(0,0,self.host.width(),max(1,self.web_rect().top()))
        return self.host.rect()

    def holes(self):
        return [r for r in [self.target, *self.extra_holes, *self.cell_holes] if not r.isEmpty()]

    def shape(self, rect, inset=0):
        bounds = QRectF(rect).adjusted(inset, inset, -inset, -inset)
        path = QPainterPath()
        if bounds.isEmpty():
            return path
        is_cell = rect in self.cell_holes or (
            rect == self.target and self.tour.key in ("hours", "boxes", "weight", "edit_any"))
        radius = min(2 if is_cell else 9, bounds.height()/2, bounds.width()/2)
        path.addRoundedRect(bounds, radius, radius)
        return path

    def badge_center(self):
        return QPoint(max(20, min(self.target.left()+12, self.width()-20)),
                      max(20, min(self.target.top()-16, self.height()-20)))

    def apply_mask(self):
        # Only the *interior* needs a binary input hole. Leave the rounded rim
        # and the number on the painted surface for subpixel antialiasing.
        mask = QRegion(self.rect())
        self.shade = QPainterPath()
        self.shade.addRect(QRectF(self.rect()))
        for hole in self.holes():
            self.shade = self.shade.subtracted(self.shape(hole))
            core = self.shape(hole, 2).toFillPolygon().toPolygon()
            mask -= QRegion(core)
        if not self.web and self.active:
            mask |= QRegion(self.card.geometry())
        self.setMask(mask)

    def highlight(self, rect):
        self.target = rect.intersected(self.host.rect() if self.web else self.rect())
        if self.web:
            self.card.hide()
            if self.tour.key == "administration":
                self.tour.owner._publish_glass_state()
            self.apply_mask()
        else:
            self.place_card()
            self.apply_mask()
            geometry = (self.size(), self.holes())
            if geometry != self._sample_geometry:
                self._sample_geometry = geometry
                self.sample_timer.start()
        if not self.web or self.tour.key == "administration":
            if self.animation.state() != self.animation.Running:
                self.animation.start()
        self.update()

    def place_card(self):
        anchor = self.anchor if self.anchor.isValid() else self.target
        margin, gap = 12, 12
        width = min(480, self.width()-2*margin)
        max_height = self.height()-2*margin
        below = self.height()-margin-anchor.bottom()-gap
        if self.anchor.isValid():
            footer = self.host._action_footer
            below = min(below, footer.mapTo(self.host, QPoint()).y()-anchor.bottom()-2*gap)
        if self.anchor.isValid() and below >= 140:
            max_height = min(max_height, below)
        self.card.fit(width, max(110, max_height))
        height = self.card.height()
        candidates = [QPoint(anchor.left(), anchor.bottom()+gap),
                      QPoint(anchor.right()+gap, anchor.top()),
                      QPoint(anchor.left(), anchor.top()-height-gap),
                      QPoint(anchor.left()-width-gap, anchor.top())]
        def fit(p):
            return QPoint(max(margin, min(p.x(), self.width()-self.card.width()-margin)),
                          max(margin, min(p.y(), self.height()-height-margin)))
        def overlap(p):
            area = QRect(p, self.card.size())
            return sum(r.width()*r.height() for hole in self.holes()
                       for r in [area.intersected(hole)] if not r.isEmpty())
        self.card.move(min(map(fit, candidates), key=overlap))
        self.card.show()
        self.card.raise_()

    def passive(self):
        self.active = False
        self.target = QRect()
        self.extra_holes = []
        self.cell_holes = []
        self.card.hide()
        self.animation.stop()
        self.apply_mask()
        self.raise_()
        self.update()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Move):
            self.setGeometry(self.host_bounds())
            self.place_gutters()
            if self.active:QTimer.singleShot(0, self.tour.position_target)
            else:self.apply_mask();self.update()
        return False

    def hideEvent(self, event):
        for gutter in self.gutters:
            if not sip.isdeleted(gutter):
                gutter.hide()
        self.animation.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        if self._sampling:
            return
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        # Masked cores expose the live controls. Both the shade and the
        # outline follow the very same contour, without an intervening gutter.
        painter.save()
        painter.setClipPath(self.shade)
        if not self.background.isNull(): painter.drawPixmap(self.rect(), self.background)
        painter.fillRect(self.rect(), QColor(5, 17, 32, 163 if self.dark else 145))
        painter.restore()
        if self.target.isEmpty() or not self.active or (self.web and self.tour.key != "administration"):
            return
        painter.setPen(QPen(QColor("#62bcff"), 2))
        for hole in self.holes():
            painter.drawPath(self.shape(hole, 1))
        center = self.badge_center()
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

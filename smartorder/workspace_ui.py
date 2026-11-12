"""Small in-window controls and scoped font scaling, without native helper windows."""
from functools import lru_cache
import json
from pathlib import Path
from PyQt5.QtCore import QByteArray, QEvent, QEasingCurve, QPropertyAnimation, QRect, QRectF, QSize, Qt
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtGui import QColor, QFontMetrics, QImageReader, QLinearGradient, QPainter, QPalette, QPixmap
from PyQt5.QtWidgets import QDialog, QFrame, QLabel, QProgressBar, QPushButton, QVBoxLayout
from .appearance import typography_qss, font_for
from .config import resource_path, network_root
from .i18n import tr
from .workshops import WORKSHOPS

def apply_page_scale(widget, appearance, zoom=100):
    key=(int(zoom),json.dumps(appearance,sort_keys=True))
    if getattr(widget,"_page_scale_key",None)==key and widget.styleSheet()==getattr(widget,"_liquid_scoped_qss",None):return
    scale=max(.5,min(2.,zoom/100));height=max(28,round(30*min(scale,1.5)))
    css=typography_qss(appearance,zoom)+f'QPushButton,QLineEdit,QComboBox,QDateEdit,QDateTimeEdit,QSpinBox,QDoubleSpinBox{{min-height:{height}px;}}QTabBar::tab{{min-height:{height}px;}}'
    base=getattr(widget,"_page_base_qss",None)
    if base is None:base=widget.styleSheet();widget._page_base_qss=base
    widget._liquid_scoped_qss=base+css
    widget.setStyleSheet(widget._liquid_scoped_qss);widget._page_scale_key=key
    align_action_sizes(widget,appearance,zoom)

def align_action_sizes(page,appearance,zoom):
    metrics=QFontMetrics(font_for("buttons",zoom,appearance))
    for button in page.findChildren(QPushButton):
        kind=button.property("alignedAction")
        if kind:
            text=tr("Добавить" if kind=="add" else "Загрузить из Excel")
            button.setFixedWidth(max(110 if kind=="add" else 190,metrics.horizontalAdvance(text)+32))
            button.setFixedHeight(max(42,metrics.height()+20))

class EmptyTableMessage(QLabel):
    def __init__(self,table,message,search=None):
        super().__init__(table.viewport());self.table,self.message,self.search=table,message,search
        self.setObjectName("EmptyTableMessage");self.setAlignment(Qt.AlignCenter);self.setWordWrap(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents);table.viewport().installEventFilter(self)
        for signal in (table.model().rowsInserted,table.model().rowsRemoved,table.model().modelReset,table.model().layoutChanged):signal.connect(self.refresh)
        if search is not None:search.textChanged.connect(self.refresh)
        self.refresh()
    def refresh(self,*_):
        message=tr("По вашему запросу ничего не найдено." if self.search is not None and self.search.text().strip() else self.message)
        self.setText(message)
        self.setGeometry(self.parentWidget().rect().adjusted(16,8,-16,-8));self.setVisible(self.table.model().rowCount()==0);self.raise_()
        self.update()
    def paintEvent(self, event):
        from .liquid_effects import theme_of
        dark = theme_of(self) == "dark"
        if getattr(self, "_icon_theme", None) != dark:
            source = resource_path("smartorder/glass/assets/empty-state.svg").read_bytes()
            if dark:source = source.replace(b"#7899b9", b"#a2bfdc")
            self._vector_icon = QSvgRenderer(QByteArray(source), self)
            self._icon_theme = dark
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setFont(self.font())
        bounds = self.fontMetrics().boundingRect(QRect(0,0,max(80,self.width()-32),400), Qt.AlignHCenter|Qt.TextWordWrap,self.text())
        height = 96 + 18 + bounds.height()
        top = max(0,(self.height()-height)//2)
        self._vector_icon.render(painter,QRectF((self.width()-96)/2,top,96,96))
        painter.setPen(QColor("#b1c6df" if dark else "#425f80"))
        painter.drawText(QRect(16,top+114,max(0,self.width()-32),bounds.height()+2),Qt.AlignHCenter|Qt.TextWordWrap,self.text())
    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Show,QEvent.Resize):self.refresh()
        return False


class StartupPaintCover(QFrame):
    """Opaque content until Chromium confirms the first populated frame."""
    def __init__(self, parent, theme):
        super().__init__(parent)
        self.setObjectName("StartupPaintCover")
        self.setProperty("plainSurface", True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.color=QColor("#15273e" if theme=="dark" else "#dcebf7")
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)
        self.show();self.raise_()
    def eventFilter(self, watched, event):
        if event.type()==QEvent.Resize:self.setGeometry(watched.rect())
        return False
    def paintEvent(self, event):
        painter=QPainter(self);painter.fillRect(self.rect(),self.color)


def reveal_after_first_frame(window, loading, callback=None):
    from PyQt5.QtCore import QTimer
    from PyQt5 import sip
    timer=QTimer(window);timer.setInterval(25)
    def ready():
        if sip.isdeleted(window) or getattr(window,"_live_closed",False):
            timer.stop()
            if not sip.isdeleted(loading):loading.close()
            return
        painted=getattr(window,"_glass_painted",True) or getattr(window,"_glass_error",False)
        if not painted or getattr(window,"_orders_running",False):return
        timer.stop();timer.deleteLater()
        loading.fade_out()
        window._startup_revealed=True
        if callback:QTimer.singleShot(250,callback)
    timer.timeout.connect(ready);timer.start()
    window._startup_reveal_timer=timer
    return timer

class ActionAccessOverlay(QFrame):
    def __init__(self,parent):
        super().__init__(parent);self.setObjectName("AnalyticsOrderOverlay")
        self.setStyleSheet("QFrame#AnalyticsOrderOverlay{background:rgba(25,51,78,235);border:1px solid #7892ae;border-radius:8px;}QLabel{color:#e7f2ff;background:transparent;}")
        layout=QVBoxLayout(self);layout.setContentsMargins(6,2,6,2)
        label=QLabel(tr("Недоступно"));label.setAlignment(Qt.AlignCenter);layout.addWidget(label)
        parent.setMinimumHeight(42);parent.installEventFilter(self);self.setGeometry(parent.rect());self.show();self.raise_()
    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Show,QEvent.Resize):self.setGeometry(watched.rect());self.raise_()
        return False

WORKSHOP_PHOTOS={"packaging":"цех упаковки.png","smoking":"цех копчения.jpg","drying":"цех сушки.png","rennet":"сычужный цех.png","adyghe":"адыгейский цех.png","cheese":"сычужный цех.png"}

def workshop_photo_path(key):
    filename=WORKSHOP_PHOTOS[key]
    candidates=[resource_path("smartorder/glass/assets/workshops/"+filename),resource_path("resources/"+filename),resource_path(filename),network_root()/"resources"/filename]
    return next((p for p in candidates if p.is_file()),None)

@lru_cache(maxsize=6)
def workshop_picture(key):
    path=workshop_photo_path(key)
    if path is None:return QPixmap()
    reader=QImageReader(str(path));size=reader.size()
    if size.isValid():size.scale(QSize(960,540),Qt.KeepAspectRatio);reader.setScaledSize(size)
    return QPixmap.fromImage(reader.read())

class WorkshopLoadingDialog(QDialog):
    def __init__(self,key,parent=None):
        super().__init__(parent,Qt.FramelessWindowHint|Qt.Tool)
        self.setProperty("plainSurface",True);self.setObjectName("WorkshopLoadingDialog");self.workshop=key
        self.picture=workshop_picture(key);self.setFixedSize(460,258);self.setModal(False);self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground,False);self.setAutoFillBackground(True)
        pal=self.palette();pal.setColor(QPalette.Window,QColor("#15273e"));self.setPalette(pal)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,24,24,22);layout.addStretch()
        self.heading=QLabel(tr(WORKSHOPS[key]));self.heading.setStyleSheet("color:white;font-size:22px;font-weight:700;background:transparent;");layout.addWidget(self.heading)
        label=QLabel(tr("Загрузка рабочего пространства…"));label.setStyleSheet("color:#e7f2ff;background:transparent;");layout.addWidget(label)
        progress=QProgressBar();progress.setRange(0,0);progress.setTextVisible(False);progress.setFixedHeight(6)
        progress.setStyleSheet("QProgressBar{background:rgba(255,255,255,65);border:0;border-radius:3px;}QProgressBar::chunk{background:#63b4ff;border-radius:3px;}");layout.addWidget(progress)
        if parent is not None:self.move(parent.frameGeometry().center()-self.rect().center())

    def fade_out(self):
        if hasattr(self, "_fade_out"):
            return self._fade_out
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(180)
        animation.setStartValue(self.windowOpacity())
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.InOutQuad)
        animation.finished.connect(self.close)
        animation.finished.connect(self.deleteLater)
        self._fade_out = animation
        animation.start()
        return animation
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor("#15273e"))
        if not self.picture.isNull():
            factor=max(self.width()/self.picture.width(),self.height()/self.picture.height());w,h=self.picture.width()*factor,self.picture.height()*factor
            painter.drawPixmap(QRectF((self.width()-w)/2,(self.height()-h)/2,w,h),self.picture,QRectF(self.picture.rect()))
        tint=QLinearGradient(0,0,0,self.height());tint.setColorAt(0,QColor(9,24,44,20));tint.setColorAt(1,QColor(9,24,44,235));painter.fillRect(self.rect(),tint)

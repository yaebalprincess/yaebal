"""Editor date popup using the same HTML, CSS and date grid as the main window."""
import json
from pathlib import Path

from PyQt5 import sip
from PyQt5.QtCore import QDate, QEvent, QObject, QPoint, QRect, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile, QWebEngineView
from PyQt5.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout

from .config import resource_path
from .i18n import language, tr
from .liquid_effects import theme_of


class CalendarBridge(QObject):
    def __init__(self, popup):
        super().__init__(popup)
        self.popup = popup

    @pyqtSlot()
    def ready(self):
        self.popup.ready = True
        if self.popup.isVisible():self.popup.publish()

    @pyqtSlot()
    def painted(self):
        self.popup.cover.hide()

    @pyqtSlot(str)
    def select(self, value):
        if not self.popup.isVisible() or len(value) != 10:return
        date = QDate.fromString(value, Qt.ISODate)
        field = self.popup.field
        if not date.isValid() or not field.minimumDate() <= date <= field.maximumDate():return
        self.popup.hide()
        field.setDate(date)
        self.popup.dateSelected.emit(date)

    @pyqtSlot()
    def cancel(self):
        self.popup.hide()


class CalendarPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, main):
        expected = resource_path("smartorder/glass/calendar.html").resolve()
        return bool(main and url.isLocalFile() and Path(url.toLocalFile()).resolve() == expected)

    def createWindow(self, kind):return None


class OrderCalendarPopup(QFrame):
    dateSelected = pyqtSignal(QDate)

    def __init__(self, field):
        super().__init__(field.window())
        self.field, self.ready = field, False
        self.setProperty("plainSurface", True)
        self.setObjectName("OrderCalendarPopup")
        self.hide()
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.NoContextMenu)
        profile = QWebEngineProfile(self.view)
        from .glass_ui import LocalAssetsOnly
        self.interceptor = LocalAssetsOnly(profile)
        profile.setUrlRequestInterceptor(self.interceptor)
        page = CalendarPage(profile, self.view)
        profile.setParent(page)
        self.view.setPage(page)
        self.channel = QWebChannel(page)
        self.bridge = CalendarBridge(self)
        self.channel.registerObject("calendar", self.bridge)
        page.setWebChannel(self.channel)
        root.addWidget(self.view)
        self.cover = QLabel(tr("Загрузка календаря…"), self)
        self.cover.setAlignment(Qt.AlignCenter)
        self._set_color()
        url = QUrl.fromLocalFile(str(resource_path("smartorder/glass/calendar.html").resolve()))
        url.setQuery("theme=" + theme_of(field))
        self.view.load(url)
        field.installEventFilter(self)
        QApplication.instance().installEventFilter(self)

    def _set_color(self):
        dark = theme_of(self.field) == "dark"
        color = "#15273e" if dark else "#dcebf7"
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(color))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.view.page().setBackgroundColor(QColor(color))
        self.cover.setStyleSheet("background:"+color+";color:"+("#e7f2ff" if dark else "#102b50")+";border:0;")

    def open(self):
        self._set_color()
        host = self.parentWidget()
        owner = self.field
        while owner is not None and not hasattr(owner,"ui_settings"):owner=owner.parentWidget()
        scale = max(.5,min(2.,owner.ui_settings.zoom/100 if owner else 1))
        width = max(330,int(350*min(1.4,scale))) + 16
        self.resize(min(width,host.width()-16),min(int(450*max(1.,min(1.4,scale))),host.height()-16))
        anchor = self.field.mapTo(host,QPoint(0,self.field.height()+4))
        x=max(8,min(anchor.x(),host.width()-self.width()-8))
        y=max(8,min(anchor.y(),host.height()-self.height()-8))
        self.move(x,y)
        self.cover.setGeometry(self.rect())
        self.cover.show()
        self.show();self.raise_();self.cover.raise_()
        if self.ready:self.publish()

    def publish(self):
        owner = self.field
        while owner is not None and not hasattr(owner,"ui_settings"):owner=owner.parentWidget()
        state={"theme":theme_of(self.field),"language":language(),"scale":owner.ui_settings.zoom/100 if owner else 1,
               "date":self.field.date().toString(Qt.ISODate),"today":QDate.currentDate().toString(Qt.ISODate)}
        state["translations"]={text:tr(text) for text in ("Сегодня","Отмена","Применить","Выберите дату наряда")}
        if owner is not None:state["appearance"]=owner.ui_settings.appearance
        self.view.page().runJavaScript("window.setCalendarState("+json.dumps(state,ensure_ascii=False)+")")

    def eventFilter(self, watched, event):
        if sip.isdeleted(self) or sip.isdeleted(self.field):return False
        if watched is self.field and event.type()==QEvent.MouseButtonPress and self.field._icon_rect().contains(event.pos()):
            self.hide() if self.isVisible() else self.open()
            return True
        if not self.isVisible():return False
        if event.type()==QEvent.KeyPress and event.key()==Qt.Key_Escape:
            self.hide();return True
        if watched is self.parentWidget() and event.type()==QEvent.Hide:self.hide()
        if watched is self.parentWidget() and event.type()==QEvent.Resize:
            QTimer.singleShot(0,lambda:self.open() if not sip.isdeleted(self) and self.isVisible() else None)
        if event.type()==QEvent.MouseButtonPress and hasattr(event,"globalPos"):
            inside=QRect(self.mapToGlobal(QPoint()),self.size()).contains(event.globalPos())
            if not inside and watched is not self.field:self.hide()
        return False


def install_order_calendar(field):
    old = field._popup
    old.hide();old.deleteLater()
    field._popup = OrderCalendarPopup(field)
    return field._popup

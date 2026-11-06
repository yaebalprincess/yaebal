"""Consistent unavailable controls, anchored popups and restrained window motion."""
from PyQt5.QtCore import Qt,QObject,QEvent,QPoint,QRect,QRectF,QTimer,QPropertyAnimation,QEasingCurve
from PyQt5.QtGui import QColor,QPainter,QPen,QPainterPath,QCursor,QRegion
from PyQt5.QtWidgets import QApplication,QWidget,QFrame,QVBoxLayout,QLabel,QToolButton,QAction,QTabBar,QAbstractButton
from .i18n import tr,apply_language
from .liquid_style import colors


class FittingTabBar(QTabBar):
    def tabSizeHint(self,index):
        from PyQt5.QtCore import QSize
        metrics=self.fontMetrics()
        return QSize(max(110,metrics.horizontalAdvance(self.tabText(index))+44),max(44,metrics.height()+22))
    def mouseMoveEvent(self,event):
        index=self.tabAt(event.pos());self.setCursor(Qt.ForbiddenCursor if index>=0 and not self.isTabEnabled(index) else Qt.ArrowCursor)
        super().mouseMoveEvent(event)


class AccessCursor(QObject):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.forbidden=False;app.installEventFilter(self)
    def eventFilter(self,widget,event):
        if not isinstance(widget,QWidget):return False
        if event.type()==QEvent.Polish and widget.metaObject().className()=="QComboBoxPrivateContainer" and not widget.property("plainSurface"):
            from PyQt5.QtWidgets import QComboBox
            if isinstance(widget.parentWidget(),QComboBox):prepare_combo_popup(widget.parentWidget())
        if event.type()==QEvent.Show:
            widget.setMouseTracking(True)
            if not widget.isEnabled():widget.setCursor(Qt.ForbiddenCursor)
        if event.type() in (QEvent.MouseMove,QEvent.HoverMove,QEvent.Enter,QEvent.Leave,QEvent.EnabledChange):
            under=self.app.widgetAt(QCursor.pos());denied=under is not None and (not under.isEnabled() or bool(under.property("accessDenied")))
            if isinstance(under,QTabBar):
                index=under.tabAt(under.mapFromGlobal(QCursor.pos()));denied=index>=0 and not under.isTabEnabled(index)
            if denied!=self.forbidden:
                if denied:self.app.setOverrideCursor(Qt.ForbiddenCursor)
                else:self.app.restoreOverrideCursor()
                self.forbidden=denied
        return False


def install_access_cursor():
    app=QApplication.instance()
    if not hasattr(app,"_access_cursor"):app._access_cursor=AccessCursor(app)


class RestrictedArea(QFrame):
    def __init__(self,parent,targets):
        super().__init__(parent);self.targets=targets;self.setProperty("accessDenied",True);self.setCursor(Qt.ForbiddenCursor)
        self.setObjectName("RestrictedArea");self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("QFrame#RestrictedArea{border:0;background:transparent;}QLabel{background:transparent;color:#6b88a5;}")
        layout=QVBoxLayout(self);label=QLabel(tr("Недоступно"));label.setAlignment(Qt.AlignCenter);layout.addWidget(label)
        for widget in [parent,*targets]:widget.installEventFilter(self)
        self.place();self.show();self.raise_()
    def place(self):
        from PyQt5 import sip
        if sip.isdeleted(self):return
        rect=QRect()
        for widget in self.targets:
            if widget.isHidden():continue
            current=QRect(widget.mapTo(self.parentWidget(),QPoint()),widget.size());rect=rect.united(current)
        self.setGeometry(rect.adjusted(-5,-5,5,5));self.raise_()
    def eventFilter(self,widget,event):
        if event.type() in (QEvent.Resize,QEvent.Move,QEvent.Show):QTimer.singleShot(0,self.place)
        return False
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        dark=getattr(getattr(self.window(),"ui_settings",None),"theme","light")=="dark"
        path=QPainterPath();path.addRoundedRect(QRectF(self.rect().adjusted(1,1,-1,-1)),12,12)
        painter.fillPath(path,QColor(25,51,78,180) if dark else QColor(229,243,255,190));painter.setClipPath(path)
        painter.setPen(QPen(QColor(143,181,215,55),1))
        for x in range(-self.height(),self.width()+self.height(),16):painter.drawLine(x,0,x-self.height(),self.height())
        painter.setClipping(False);painter.setPen(QColor(163,199,231,160));painter.drawPath(path)


class WorkshopPopup(QFrame):
    def __init__(self,owner):
        super().__init__(owner,Qt.Popup|Qt.FramelessWindowHint|Qt.NoDropShadowWindowHint)
        self.owner=owner;self._actions=[];self.setProperty("plainSurface",True);self.setObjectName("WorkshopPopup")
        c=colors(owner.ui_settings.theme=="dark");self.setStyleSheet(f'QFrame#WorkshopPopup{{background:{c["table"]};border:1px solid {c["edge"]};border-radius:12px;}}QToolButton{{text-align:left;padding:9px 12px;border:0;background:transparent;color:{c["ink"]};}}QToolButton:hover{{background:{c["hover"]};}}QToolButton:disabled{{color:{c["disabled"]};}}QLabel{{background:transparent;color:{c["muted"]};}}')
        layout=QVBoxLayout(self);layout.setContentsMargins(8,8,8,8);layout.setSpacing(2)
        header=QLabel(owner.user.username+" · "+" · ".join(tr(role) for role in owner.user.roles));header.setWordWrap(True);layout.addWidget(header)
        from .workshops import WORKSHOPS,allowed_workshops
        from .symbols import WORKSHOP_SYMBOLS,symbol_icon
        for key,title in WORKSHOPS.items():
            action=QAction(symbol_icon(WORKSHOP_SYMBOLS[key],owner.ui_settings.theme),tr(title),self);action.setData(key);action.setCheckable(True);action.setChecked(key==owner.workshop);action.setEnabled(key in allowed_workshops(owner.user))
            action.triggered.connect(lambda _,k=key:self.select(k));self._actions.append(action)
            button=QToolButton();button.setDefaultAction(action);button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.setCursor(Qt.PointingHandCursor if action.isEnabled() else Qt.ForbiddenCursor);layout.addWidget(button)
        self.setFixedWidth(max(290,min(480,owner.titlebar.badge.width())));apply_language(self)
    def actions(self):return self._actions
    def select(self,key):self.close();self.owner._switch_to_workshop(key)
    def popup(self,point):
        self.adjustSize();screen=QApplication.screenAt(point) or QApplication.primaryScreen();available=screen.availableGeometry()
        x=max(available.left(),min(point.x(),available.right()-self.width()+1))
        y=point.y() if point.y()+self.height()<=available.bottom() else max(available.top(),point.y()-self.height()-self.owner.titlebar.badge.height())
        self._target_position=QPoint(x,y);self.move(x,y);self.show();self.move(x,y)
        QTimer.singleShot(0,self._anchor_after_layout)
    def _anchor_after_layout(self):
        from PyQt5 import sip
        if not sip.isdeleted(self) and self.isVisible():self.move(self._target_position)


def prepare_combo_popup(combo):
    from .liquid_effects import theme_of
    c=colors(theme_of(combo)=="dark")
    view=combo.view();frame=view.window();frame.setProperty("plainSurface",True)
    frame.setWindowFlag(Qt.NoDropShadowWindowHint,True);frame.setWindowFlag(Qt.FramelessWindowHint,True)
    if isinstance(frame,QFrame):frame.setFrameShape(QFrame.NoFrame)
    frame.setStyleSheet(f'QFrame{{border:0;background:{c["table"]};}}')
    view.setStyleSheet(f'QAbstractItemView{{background:{c["table"]};color:{c["ink"]};border:1px solid {c["line"]};border-radius:8px;outline:0;padding:5px;selection-background-color:{c["selected"]};selection-color:{c["blue"]};}}QAbstractItemView::item{{min-height:30px;padding:4px 8px;}}')
    view.viewport().setAutoFillBackground(True)


class WindowMotion(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.animation=None
    def toggle(self,fullscreen=True):
        if self.animation is not None and self.animation.state()==QPropertyAnimation.Running:return
        window=self.window;screen=window.screen() or QApplication.primaryScreen()
        entering=not (window.isFullScreen() if fullscreen else window.isMaximized())
        if fullscreen and entering:
            self.full_restore_rect=QRect(window.geometry());self.full_restore_maximized=window.isMaximized()
        elif not fullscreen and entering:self.normal_restore_rect=QRect(window.geometry())
        current=QRect(window.geometry())
        if entering:target=screen.geometry() if fullscreen else screen.availableGeometry()
        elif fullscreen:target=screen.availableGeometry() if getattr(self,"full_restore_maximized",False) else getattr(self,"full_restore_rect",window.normalGeometry())
        else:target=getattr(self,"normal_restore_rect",window.normalGeometry())
        window.setUpdatesEnabled(False)
        try:
            if window.isFullScreen() or window.isMaximized():window.showNormal()
            window.setGeometry(current)
        finally:window.setUpdatesEnabled(True)
        animation=QPropertyAnimation(window,b"geometry",self);self.animation=animation
        animation.setDuration(165);animation.setEasingCurve(QEasingCurve.OutCubic);animation.setStartValue(current);animation.setEndValue(target)
        def finish():
            if fullscreen and entering:window.showFullScreen()
            elif entering or fullscreen and getattr(self,"full_restore_maximized",False):window.showMaximized()
            else:window.showNormal()
            window.fullscreen_hint_label.setText(tr("Esc — выйти из полноэкранного режима" if window.isFullScreen() else "Esc — для полноэкранного режима"))
            window._apply_native_titlebars()
            if hasattr(window,"_schedule_glass_state"):window._schedule_glass_state()
            self.animation=None;animation.deleteLater()
        animation.finished.connect(finish);animation.start()


def align_order_footer(dialog):
    from PyQt5.QtWidgets import QHBoxLayout,QPushButton,QDialogButtonBox,QScrollArea
    if getattr(dialog,"_aligned_footer",False):return
    names={"Добавить работников","Добавить работы","Удалить выбранных","Выгрузить в Excel","Выгрузить в EXCEL"}
    buttons=[button for button in dialog.findChildren(QPushButton) if button.text() in names]
    boxes=[box for box in dialog.findChildren(QDialogButtonBox) if any(b.text() in {"Сохранить","Отмена"} for b in box.buttons())]
    if not buttons or not boxes:return
    def detach(layout,widget):
        layout.removeWidget(widget)
        for i in range(layout.count()):
            child=layout.itemAt(i).layout()
            if child is not None:detach(child,widget)
    layout=dialog.layout();box=boxes[-1]
    for widget in [*buttons,box]:
        parent=widget.parentWidget()
        if parent is not None and parent.layout() is not None:detach(parent.layout(),widget)
    content=QWidget();row=QHBoxLayout(content);row.setContentsMargins(0,0,0,0);row.setSpacing(8)
    export=[b for b in buttons if b.text().startswith("Выгрузить")]
    for button in buttons:
        if button not in export:row.addWidget(button)
    row.addStretch();row.addWidget(box)
    for button in export:row.addWidget(button)
    for button in [*buttons,*box.buttons()]:button.setFixedHeight(max(42,button.fontMetrics().height()+20))
    scroll=QScrollArea();scroll.setObjectName("OrderActionFooter");scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(content);scroll.setFixedHeight(max(b.height() for b in [*buttons,*box.buttons()])+18);layout.addWidget(scroll)
    dialog._aligned_footer=True;dialog._action_footer=scroll

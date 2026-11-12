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
        return QSize(max(110,metrics.horizontalAdvance(self.tabText(index))+2*int(self.property("tabHorizontalPadding") or 22)+12),max(44,metrics.height()+22))
    def mouseMoveEvent(self,event):
        index=self.tabAt(event.pos());self.setCursor(Qt.ForbiddenCursor if index>=0 and not self.isTabEnabled(index) else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        from .liquid_effects import theme_of

        dark = theme_of(self) == "dark"
        palette = colors(dark)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for index in range(self.count()):
            rect = QRectF(self.tabRect(index)).adjusted(.5, 1.5, -1.5, -1.5)
            if not rect.intersects(QRectF(event.rect())):
                continue
            selected = index == self.currentIndex()
            fill = QColor("#244562" if selected else "#1a304a") if dark else QColor("#f5fbff" if selected else "#dcecf9")
            fill.setAlpha(225 if selected else 160)
            line = QColor("#56799c" if dark else "#9dbddc")
            line.setAlpha(160)
            painter.setBrush(fill)
            painter.setPen(QPen(line, 1))
            painter.drawRoundedRect(rect, 8, 8)
            role = "disabled" if not self.isTabEnabled(index) else "blue" if selected else "muted"
            painter.setPen(QColor(palette[role]))
            painter.drawText(rect, Qt.AlignCenter | Qt.TextShowMnemonic, self.tabText(index))


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
        if event.type()==QEvent.EnabledChange and widget.isEnabled() and not widget.property("accessDenied") and widget.cursor().shape()==Qt.ForbiddenCursor:widget.unsetCursor()
        if event.type() in (QEvent.MouseMove,QEvent.HoverMove,QEvent.Enter,QEvent.Leave,QEvent.EnabledChange):
            under=self.app.widgetAt(QCursor.pos());denied=under is not None and (not under.isEnabled() or bool(under.property("accessDenied")))
            from PyQt5.QtWidgets import QMenu,QAbstractItemView
            if isinstance(under,QMenu):
                action=under.actionAt(under.mapFromGlobal(QCursor.pos()));denied=action is not None and not action.isEnabled()
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
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.running = False
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(36)
        self._settle.timeout.connect(self._finish)
        window.installEventFilter(self)

    def toggle(self, fullscreen=True):
        if self.running:
            return
        from .liquid_effects import transition_to

        window = self.window
        if fullscreen:
            if window.isFullScreen():
                mode = getattr(self, "before_fullscreen_mode", Qt.WindowNoState)
            else:
                self.before_fullscreen_mode = Qt.WindowMaximized if window.isMaximized() else Qt.WindowNoState
                mode = Qt.WindowFullScreen
        else:
            mode = Qt.WindowNoState if window.isMaximized() else Qt.WindowMaximized

        feedback = getattr(window, "_fullscreen_feedback", None)
        if feedback is not None:
            feedback.hide()
        self._frame = transition_to(window, window.grab(), hold=True)
        self._show_feedback = fullscreen
        self.running = True
        # Commit the final native mode once. The fading child covers the
        # renderer until the window manager has delivered the new geometry.
        window.setWindowState(mode)
        self._settle.start()

    def eventFilter(self, watched, event):
        if self.running and event.type() == QEvent.Resize:
            self._settle.start()
        return False

    def _finish(self):
        window = self.window
        frame, self._frame = self._frame, None
        self.running = False
        if not window.isVisible():
            if frame is not None:
                frame.dismiss()
            return
        fullscreen = window.isFullScreen()
        hint = "Esc — выйти из полноэкранного режима" if fullscreen else "Esc — для полноэкранного режима"
        window.fullscreen_hint_label.setText(tr(hint))
        if hasattr(window, "_schedule_glass_state"):
            window._schedule_glass_state()
        if frame is not None:
            frame.fade(.24)
        if self._show_feedback:
            window._show_fullscreen_feedback(fullscreen)


def align_order_footer(dialog):
    from PyQt5.QtWidgets import QHBoxLayout,QPushButton,QDialogButtonBox,QScrollArea
    if getattr(dialog,"_aligned_footer",False):return
    names={"Добавить работников","Добавить работы","Удалить выбранных","Выгрузить в Excel","Выгрузить в EXCEL"}
    buttons=[button for button in dialog.findChildren(QPushButton) if button.text() in names]
    export_group = getattr(dialog, "export_actions", None)
    if export_group is not None:
        buttons = [button for button in buttons if button is not dialog.export_current_btn]
    boxes=[box for box in dialog.findChildren(QDialogButtonBox) if any(b.text() in {"Сохранить","Отмена"} for b in box.buttons())]
    if not buttons or not boxes:return
    def detach(layout,widget):
        layout.removeWidget(widget)
        for i in range(layout.count()):
            child=layout.itemAt(i).layout()
            if child is not None:detach(child,widget)
    layout=dialog.layout();box=boxes[-1]
    for widget in [*buttons,box, *([export_group] if export_group is not None else [])]:
        parent=widget.parentWidget()
        if parent is not None and parent.layout() is not None:detach(parent.layout(),widget)
    content=QWidget();row=QHBoxLayout(content);row.setContentsMargins(0,0,0,0);row.setSpacing(8)
    export=[b for b in buttons if b.text().startswith("Выгрузить")]
    for button in buttons:
        if button not in export:row.addWidget(button)
    row.addStretch();row.addWidget(box)
    for button in export:row.addWidget(button)
    if export_group is not None:
        row.addWidget(export_group)
        height = max(42, dialog.export_current_btn.fontMetrics().height() + 20)
        export_group.setFixedHeight(height)
        for button in export_group.findChildren(QPushButton):
            button.setFixedHeight(height - 2)
    for button in [*buttons,*box.buttons()]:button.setFixedHeight(max(42,button.fontMetrics().height()+20))
    scroll=QScrollArea();scroll.setObjectName("OrderActionFooter");scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(content);scroll.setFixedHeight(max(b.height() for b in [*buttons,*box.buttons()])+18);layout.addWidget(scroll)
    dialog._aligned_footer=True;dialog._action_footer=scroll

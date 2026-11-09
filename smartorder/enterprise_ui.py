"""RC20 additions on top of the existing, tested RC18 desktop UI."""
from __future__ import annotations
from .i18n import source_text, tr

import logging
import json
import os
import time
import threading
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QEvent, QObject, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve, pyqtProperty, QUrl
from PyQt5.QtGui import QColor, QPainter, QPen, QLinearGradient, QRadialGradient, QPainterPath, QFont, QDesktopServices
from PyQt5.QtWidgets import (QApplication, QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSizePolicy,
    QDialog, QDialogButtonBox, QRadioButton, QButtonGroup, QScrollArea, QSizeGrip, QTextBrowser, QMessageBox, QMenu, QActionGroup, QToolButton, QListWidgetItem, QProgressBar)

from . import heavy_ui
from .heavy_ui import RC18MainWindow, _set_logo, _RC18SupportDialog
from .config import APP_VERSION, network_root, resource_path, set_active_workshop, local_state_dir, local_drafts_dir
from .security import ALL_PERMISSIONS, SessionUser, Permission, ANALYTICS_ROLES, ANALYTICS_ONLY_ROLES, ACCOUNTING_ROLES, WORKSHOP_ROLES, split_roles
from .workshops import WorkshopManager, WorkshopDatabase, SessionTracker, WORKSHOPS, allowed_workshops
from .analytics_ui import AnalyticsWidget
from .symbols import symbol_icon, WORKSHOP_SYMBOLS


class TabMotion(QWidget):
    """Overlay animates hover, press and selection while native tabs retain behavior."""
    def __init__(self,bar):
        super().__init__(bar);self.bar=bar;self._rect=QRectF();self._hover=-1;self._pressed=False;self._amount=0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents);self.setAttribute(Qt.WA_NoSystemBackground);bar.setMouseTracking(True);bar.installEventFilter(self)
        self.anim=QPropertyAnimation(self,b"selection",self);self.anim.setDuration(220);self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.hover_anim=QPropertyAnimation(self,b"hoverAmount",self);self.hover_anim.setDuration(150);self.hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._pointer = QPointF()
        self._press_point = QPointF()
        self._wave = 1.0
        self.wave_anim = QPropertyAnimation(self, b"wave", self)
        self.wave_anim.setDuration(480)
        self.wave_anim.setEasingCurve(QEasingCurve.OutCubic)
        bar.currentChanged.connect(self.select);self.select(bar.currentIndex());self.show()
    def get_rect(self):return self._rect
    def set_rect(self,r):self._rect=r;self.update()
    selection=pyqtProperty(QRectF,get_rect,set_rect)
    def get_amount(self):return self._amount
    def set_amount(self,v):self._amount=v;self.update()
    hoverAmount=pyqtProperty(float,get_amount,set_amount)
    def get_wave(self):return self._wave
    def set_wave(self,value):self._wave=value;self.update()
    wave=pyqtProperty(float,get_wave,set_wave)
    def fade_hover(self,value):
        self.hover_anim.stop();self.hover_anim.setStartValue(self._amount);self.hover_anim.setEndValue(float(value));self.hover_anim.start()
    def select(self,index):
        self.setGeometry(self.bar.rect());self.raise_()
        target=QRectF(self.bar.tabRect(index));self.anim.stop();self.anim.setStartValue(self._rect if not self._rect.isNull() else target);self.anim.setEndValue(target);self.anim.start()
    def eventFilter(self,obj,event):
        t=event.type()
        if t==QEvent.Resize:self.setGeometry(self.bar.rect());self._rect=QRectF(self.bar.tabRect(self.bar.currentIndex()))
        elif t==QEvent.MouseMove:
            self._pointer = QPointF(event.pos())
            index=self.bar.tabAt(event.pos())
            if index!=self._hover or self._amount==0:self._hover=index;self.fade_hover(17)
            self.update()
        elif t==QEvent.Leave:self.fade_hover(0)
        elif t==QEvent.MouseButtonPress:
            self._pressed=True;self._hover=self.bar.tabAt(event.pos());self.fade_hover(45)
            self._press_point=QPointF(event.pos())
            self.wave_anim.stop();self.wave_anim.setStartValue(0.0);self.wave_anim.setEndValue(1.0);self.wave_anim.start()
        elif t==QEvent.MouseButtonRelease:self._pressed=False;self.fade_hover(17)
        return False
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        if self._hover>=0 and self.bar.isTabEnabled(self._hover):
            r=QRectF(self.bar.tabRect(self._hover)).adjusted(2,2,-2,-2)
            path=QPainterPath();path.addRoundedRect(r,8,8)
            glow=QRadialGradient(self._pointer,max(70,r.width()*.72))
            glow.setColorAt(0,QColor(255,255,255,min(150,int(self._amount*5))))
            glow.setColorAt(1,QColor(7,133,255,0));p.fillPath(path,glow)
            if self._wave<1:
                wave=QRadialGradient(self._press_point,max(1,r.width()*self._wave))
                wave.setColorAt(0,QColor(255,255,255,int(100*(1-self._wave))))
                wave.setColorAt(1,QColor(160,220,255,0));p.fillPath(path,wave)
        r=self._rect.adjusted(10,self._rect.height()-4,-10,-1)
        gradient=QLinearGradient(r.topLeft(),r.topRight());gradient.setColorAt(0,QColor("#00b7da"));gradient.setColorAt(.65,QColor("#0786ff"));gradient.setColorAt(1,QColor("#9d86f3"));p.setPen(Qt.NoPen);p.setBrush(gradient);p.drawRoundedRect(r,2,2)


class CaptionButton(QToolButton):
    """Always-visible standard caption symbols, independent of DWM painting."""
    def __init__(self, kind, titlebar):
        super().__init__(titlebar)
        self.kind, self.titlebar = kind, titlebar
        self.setObjectName("WindowClose" if kind == "close" else "WindowControl")
        self.setFixedSize(46, 48)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip({"min":"Свернуть", "max":"Развернуть / восстановить", "close":"Закрыть"}[kind])
        self.setAccessibleName(self.toolTip())

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = "#FFFFFF" if self.kind == "close" and self.underMouse() else ("#F0F3FA" if self.titlebar.dark else "#243149")
        painter.setPen(QPen(QColor(color), 1))
        x, y = self.width() // 2 - 5, self.height() // 2 - 5
        if self.kind == "min":
            painter.drawLine(x, y + 5, x + 10, y + 5)
        elif self.kind == "close":
            painter.drawLine(x, y, x + 10, y + 10)
            painter.drawLine(x + 10, y, x, y + 10)
        elif self.titlebar.owner.isMaximized() or self.titlebar.owner.isFullScreen():
            painter.drawLine(x + 3, y, x + 10, y)
            painter.drawLine(x + 10, y, x + 10, y + 7)
            painter.drawLine(x + 8, y + 7, x + 10, y + 7)
            painter.drawRect(x, y + 3, 7, 7)
        else:
            painter.drawRect(x, y, 10, 10)


class TitleBar(QFrame):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.drag=None;self.setObjectName("EnterpriseTitleBar");self.setFixedHeight(48)
        row=QHBoxLayout(self);row.setContentsMargins(10,0,0,0);row.setSpacing(0)
        self.title=QLabel("Smart Order — Формирование нарядов на работу")
        self.title.setObjectName("WindowTitleLabel")
        self.title.setMinimumWidth(80);self.title.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        self.title.setToolTip(self.title.text());row.addWidget(self.title,1);row.addStretch()
        self.bell=QPushButton("🔔");self.bell.setObjectName("NotificationBell");self.bell.setToolTip("Уведомления об изменениях Ваших нарядов");self.bell.clicked.connect(owner.show_notifications);self.bell.setVisible(owner.can(Permission.NOTIFICATIONS_VIEW));row.addWidget(self.bell)
        # Keep the theme switch beside the account/workshop badge, where it
        # remains reachable at every content zoom level.
        owner.theme_caption.setObjectName("TitleThemeCaption")
        row.addWidget(owner.theme_caption)
        row.addWidget(owner.theme)
        row.addSpacing(20)
        self.badge=QPushButton(f"{owner.user.username}  ·  {tr(WORKSHOPS[owner.workshop])}  ▾");self.badge.setObjectName("UserWorkshopBadge");self.badge.setProperty("symbolIcon", "user");self.badge.setIcon(symbol_icon("user", owner.ui_settings.theme));self.badge.setToolTip(f"{owner.user.role}\nНажмите, чтобы выбрать цех");self.badge.clicked.connect(owner.choose_workshop);self.badge.setEnabled(bool(allowed_workshops(owner.user)));row.addWidget(self.badge)
        row.addSpacing(8)
        self.controls=[]
        for kind,callback in [("min",owner.showMinimized),("max",self.toggle_max),("close",owner.close)]:
            button=CaptionButton(kind,self);button.clicked.connect(callback);row.addWidget(button);self.controls.append(button)
        self.set_theme(owner.ui_settings.theme)
    def set_theme(self, theme):
        from .liquid_style import colors
        self.dark = theme == "dark"
        c = colors(self.dark)
        self.setStyleSheet(f"""
QFrame#EnterpriseTitleBar{{background:{c['glass']};border:0;border-bottom:1px solid {c['edge']};}}
QLabel{{color:{c['ink']};background:transparent;}}
QLabel#TitleThemeCaption{{color:{c['muted']};padding-left:12px;padding-right:8px;}}
QPushButton#UserWorkshopBadge{{color:{c['ink']};background:{c['field']};border:1px solid {c['edge']};border-radius:9px;padding:3px 10px;min-height:24px;}}
QPushButton#UserWorkshopBadge:hover{{background:{c['hover']};border-color:#65aff5;}}
QToolButton#WindowControl,QToolButton#WindowClose{{border:0;background:transparent;padding:0;border-radius:6px;min-width:38px;max-width:38px;min-height:32px;max-height:32px;}}
QToolButton#WindowControl:hover{{background:{c['hover']};}}
QToolButton#WindowClose:hover{{background:#e04e62;color:white;}}
""")
        for button in self.controls:
            button.setFixedSize(38, 32)
            button.update()
    def toggle_max(self):
        self.owner.toggle_window_mode(self.owner.isFullScreen())
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:self.toggle_max()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            handle=self.owner.windowHandle()
            if handle is not None and hasattr(handle,"startSystemMove") and handle.startSystemMove():return
            self.drag=event.globalPos()-self.owner.frameGeometry().topLeft()
    def mouseMoveEvent(self,event):
        if self.drag is not None and event.buttons()&Qt.LeftButton and not self.owner.isMaximized() and not self.owner.isFullScreen():self.owner.move(event.globalPos()-self.drag)
    def mouseReleaseEvent(self,event):self.drag=None


class WorkshopDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.setWindowTitle("Выбор цеха");self.setMinimumWidth(490)
        root=QVBoxLayout(self);title=QLabel("Рабочее пространство");title.setStyleSheet("font-size:22px;font-weight:800;");root.addWidget(title)
        root.addWidget(QLabel(f"👤 {owner.user.username} · {owner.user.role}"));self.buttons=QButtonGroup(self);self.keys=list(WORKSHOPS)
        allowed=allowed_workshops(owner.user)
        for i,(k,v) in enumerate(WORKSHOPS.items()):
            b=QRadioButton(v+ (" · нет доступа" if k not in allowed else ""));b.setProperty("symbolIcon", WORKSHOP_SYMBOLS[k]);b.setIcon(symbol_icon(WORKSHOP_SYMBOLS[k], owner.ui_settings.theme));b.setEnabled(k in allowed);b.setChecked(k==owner.workshop);b.setMinimumHeight(35);self.buttons.addButton(b,i);root.addWidget(b)
        note=QLabel("В каждом цехе своя номенклатура, сотрудники, мастера, наряды и черновики. Учётные записи общие.");note.setWordWrap(True);root.addWidget(note)
        box=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);box.button(QDialogButtonBox.Ok).setText("Перейти в цех");box.accepted.connect(self.accept);box.rejected.connect(self.reject);root.addWidget(box)
    def selected(self):return self.keys[self.buttons.checkedId()]


def read_news():
    # Never open a shared TXT in an external editor. OS read/write rights are
    # administered separately; the application exposes a read-only viewer only.
    configured=network_root()/"UPDATE_NEWS.txt"
    path=configured if configured.exists() else resource_path("UPDATE_NEWS.txt")
    raw=path.read_bytes()
    try:return path,raw.decode("utf-8-sig")
    except UnicodeDecodeError:return path,raw.decode("cp1251")


def read_update_announcement():
    """Read the shared update notice without opening or modifying the DB."""
    path=network_root()/"UPDATE_ANNOUNCEMENT.json"
    try:
        raw=path.read_bytes()
        if len(raw)>128*1024:return None
        data=json.loads(raw.decode("utf-8"));version=str(data.get("version","")).strip()
        if not version:return None
        return {"version":version,"title":str(data.get("title","")).strip(),"description":str(data.get("description","")).strip(),"created_at":str(data.get("created_at","")).strip()}
    except Exception:return None


class MainWindow(RC18MainWindow):
    def __init__(self,db,user,manager=None,tracker=None):
        self.workshop_manager=manager or (db.manager if isinstance(db,WorkshopDatabase) else WorkshopManager(db))
        allowed=allowed_workshops(user)
        if not allowed:raise RuntimeError("У роли нет доступных цехов. Обратитесь к администратору.")
        if isinstance(db,WorkshopDatabase):
            key=db.workshop if db.workshop in allowed else allowed[0]
            if key!=db.workshop:db=self.workshop_manager.database(key,user)
        else:
            try:key=(local_state_dir()/f"workshop_{user.id}.txt").read_text().strip()
            except Exception:key=allowed[0]
            if key not in allowed:key=allowed[0]
            db=self.workshop_manager.database(key,user)
        self.workshop=key;set_active_workshop(key);self.session_tracker=tracker or SessionTracker(self.workshop_manager,user,key)
        self._initial_ui_settings = getattr(self.session_tracker, "ui_settings", None)
        from .config import SettingsStore
        from .profile_sync import load_shared_settings
        local=self._initial_ui_settings or SettingsStore(user.id,user.username).load()
        self._initial_ui_settings,self._profile_sync_status=load_shared_settings(self.workshop_manager.auth,user,local)
        self._switching=False;self._heartbeat_running=False;self.analytics=None
        self._notification_items=[];self._notification_count=0;self._notification_loading=False;self.notification_popup=None
        super().__init__(db,user)
        self.session_tracker.ui_settings = self.ui_settings
        from .profile_sync import ProfileSync
        self.profile_sync=ProfileSync(self)
        self._theme_clock = QTimer(self)
        self._theme_clock.setInterval(30000)
        self._theme_clock.timeout.connect(self._apply_scheduled_theme)
        self._theme_clock.start()
        self.setWindowTitle("Smart Order — Формирование нарядов на работу")
        if os.name!="nt":self.setWindowFlags(self.windowFlags()|Qt.FramelessWindowHint)
        self._telemetry_timer=QTimer(self);self._telemetry_timer.setInterval(60000);self._telemetry_timer.timeout.connect(self._heartbeat);self._telemetry_timer.start()
        from .live_ui import _NotificationSignals
        self._notification_signals=_NotificationSignals(self);self._notification_signals.loaded.connect(self._notifications_loaded)
        self._notification_timer=QTimer(self);self._notification_timer.setInterval(3000);self._notification_timer.timeout.connect(self.refresh_notifications)
        if self.can(Permission.NOTIFICATIONS_VIEW):
            self._notification_timer.start();QTimer.singleShot(300,self.refresh_notifications)
        from .desktop_live import DesktopSignals
        self._live_signals=DesktopSignals(self)
        self._section_generations={};self._section_jobs={};self._section_pending={}
        self._live_signals.section.connect(self._section_loaded)
        self._live_signals.orders.connect(self._orders_loaded);self._live_signals.history.connect(self._history_loaded)
        self._live_signals.watch.connect(self._live_checked);self._live_signals.order_file.connect(self._order_file_loaded)
        self._orders_generation=0;self._orders_running=False;self._orders_pending=None;self._history_generation=0
        self._live_tokens=None;self._live_closed=False;self._file_loading=False
        self._rc12_watch_timer.setInterval(1500)
        for archive_key in allowed_workshops(user):self.workshop_manager.archive_publisher.request(archive_key,self.workshop_manager._databases[archive_key])
        self._archive_retry_at=0.0
        self._account_timer=QTimer(self);self._account_timer.setInterval(5000);self._account_timer.timeout.connect(self._read_account_access)
        if user.id>0:self._account_timer.start()
        try:(local_state_dir()/f"workshop_{user.id}.txt").write_text(key)
        except OSError:pass

    def _read_account_access(self):
        from .account_store import account_snapshot
        auth,uid=self.workshop_manager.auth,self.user.id
        if uid>0:self._read_section("account_access",lambda:account_snapshot(auth,uid))

    def _apply_account_access(self,user):
        signature=(user.username,user.role,tuple(sorted(user.permissions))) if user is not None else ("disabled",self.user.id)
        current=(self.user.username,self.user.role,tuple(sorted(self.user.permissions))) if getattr(self,"_account_active",True) else ("disabled",self.user.id)
        if signature==current:return
        self._account_active=user is not None
        if user is None:user=SessionUser(self.user.id,self.user.username,self.user.role,frozenset())
        self.user=user;self.db.user=user;self.session_tracker.user=user
        self._update_permission_controls()
        if not user.can(Permission.ORDERS_VIEW):
            self._orders_generation+=1;self._orders_pending=None;self._display_orders=None;self.orders_table.report_model.set_rows([]);self.info_users_list.clear()
        if 3 in self._loaded_tabs:
            host=self.tabs.widget(3);self._apply_admin_permissions(host);self._visible_users=None;self.refresh_users();self.refresh_audit()
        for index,prefix in ((1,"catalog"),(2,"employees")):
            if index in self._loaded_tabs:
                for button in self.tabs.widget(index).findChildren(QPushButton):
                    kind=button.property("alignedAction")
                    if kind:button.setEnabled(self.can(prefix+(".create" if kind=="add" else ".import")))
                self._reference_permissions(prefix)
        self.titlebar.badge.setText(f"{user.username}  ·  {tr(WORKSHOPS[self.workshop])}  ▾")
        self.titlebar.badge.setToolTip(user.role if self._account_active else tr("Учётная запись отключена. Войдите заново."))
        choices=allowed_workshops(user)
        if self._account_active and self.workshop not in choices and choices:self._switch_to_workshop(choices[0])
        elif self._account_active and self.can(Permission.ORDERS_VIEW):self.refresh_orders()
        if self.analytics is not None:
            self.analytics.user=user
            self.analytics.export.setEnabled(bool(self.analytics.report) and user.can(Permission.ANALYTICS_EXPORT))
            if user.can(Permission.ANALYTICS_VIEW):
                self.analytics=AnalyticsWidget(self);self._replace_tab(4,self.analytics,"Аналитика")
            self._rc12_dirty_tabs.add(4)
        if hasattr(self,"_schedule_glass_state"):self._schedule_glass_state()

    def _read_section(self,name,reader):
        if not hasattr(self,'_live_signals') or self._live_closed:return
        generation=self._section_generations.get(name,0)+1;self._section_generations[name]=generation
        self._section_pending[name]=(generation,reader)
        self._start_section(name)

    def _start_section(self,name):
        if self._section_jobs.get(name) or name not in self._section_pending:return
        generation,reader=self._section_pending.pop(name);self._section_jobs[name]=True
        signals=self._live_signals
        def worker():
            try:data=reader();error=''
            except Exception as exc:data=None;error=str(exc)
            try:signals.section.emit(name,generation,data,error)
            except RuntimeError:pass
        threading.Thread(target=worker,name='SmartOrderRead_'+name,daemon=True).start()

    def _section_loaded(self,name,generation,data,error):
        self._section_jobs[name]=False
        if self._live_closed:return
        if name in self._section_pending:self._start_section(name);return
        if generation!=self._section_generations.get(name):return
        if error:logging.warning('Раздел %s временно недоступен: %s',name,error);return
        getattr(self,'_apply_'+name)(data)

    def refresh_users(self):
        if not hasattr(self,'users_table') or not (self.can(Permission.USERS_VIEW) or self.can(Permission.USERS_MANAGE)):return
        db=self.db
        self._read_section('users',lambda:[tuple(r) for r in db.list_users()])

    def _apply_users(self,rows):
        if rows==getattr(self,'_visible_users',None):return
        self._visible_users=rows;self.users_table.setUpdatesEnabled(False);self.users_table.setRowCount(len(rows));self.users_table.setColumnWidth(3,430)
        admin=self.can(Permission.USERS_MANAGE)
        from .heavy_styles import set_theme_recursive
        try:
            for i,r in enumerate(rows):
                uid,username,role,active=int(r[0]),str(r[1]),";".join(split_roles(r[2])),bool(r[3])
                self.users_table.setItem(i,0,heavy_ui.make_item(username,uid));self.users_table.setItem(i,1,heavy_ui.make_item(role));self.users_table.setItem(i,2,heavy_ui.make_item(('Активируется '+str(r[4]).replace('T',' ')) if len(r)>4 and r[4] else ('Активен' if active else 'Отключён')))
                target=frozenset(json.loads(r[5])) if len(r)>5 and r[5] is not None else self.workshop_manager.auth.role_permissions(role)
                can_manage=admin and (self.can(Permission.PERMISSIONS_MANAGE) or target<=self.user.permissions)
                host=QWidget();host.setProperty("targetPermissions",list(target));host.setProperty("hasManagementHandlers",can_manage)
                h=QHBoxLayout(host);h.setContentsMargins(4,4,4,4);h.setSpacing(8)
                edit=QPushButton('Изменить');edit.setObjectName('UserEditButton');delete=QPushButton('Удалить');delete.setObjectName('UserDeleteButton');toggle=QPushButton('Отключить' if active else 'Включить');toggle.setObjectName('UserToggleButton')
                for button in (edit,delete,toggle):button.setEnabled(can_manage);h.addWidget(button)
                if can_manage:
                    edit.clicked.connect(lambda _,u=uid,n=username,rn=role:self._edit_user_by_id(u,n,rn));delete.clicked.connect(lambda _,u=uid,n=username:self._delete_user_by_id(u,n));toggle.clicked.connect(lambda _,u=uid,a=active:self._toggle_user_by_id(u,a))
                h.addStretch();self.users_table.setCellWidget(i,3,host);self.users_table.setRowHeight(i,62)
                set_theme_recursive(host,self.ui_settings.theme)
        finally:self.users_table.setUpdatesEnabled(True)

    def _rc18_reload_audit_users(self):
        # Filled by the same background read as the audit rows.
        if hasattr(self,'audit_table'):self.refresh_audit()

    def refresh_audit(self):
        if not hasattr(self,'audit_table') or not self.can(Permission.AUDIT_VIEW):return
        start=self.audit_date_filter.startDate().toString('yyyy-MM-dd') if hasattr(self,'audit_date_filter') else None
        end=self.audit_date_filter.endDate().toString('yyyy-MM-dd') if hasattr(self,'audit_date_filter') else None
        user=self.audit_user_filter.currentData() if hasattr(self,'audit_user_filter') else None
        db=self.db
        self._read_section('audit',lambda:([tuple(r) for r in db.recent_audit_filtered(start,end,user,1000)],db.audit_usernames()))

    def _apply_audit(self,data):
        rows,users=data
        if hasattr(self,'audit_user_filter'):
            combo=self.audit_user_filter;previous=combo.currentData();combo.blockSignals(True)
            combo.clear();combo.addItem('Все пользователи',None)
            for username in users:combo.addItem(username,username)
            combo.setCurrentIndex(max(0,combo.findData(previous)));combo.blockSignals(False)
        if rows==getattr(self,'_visible_audit',None):return
        self._visible_audit=rows;self.audit_table.setUpdatesEnabled(False);self.audit_table.setRowCount(len(rows))
        try:
            for i,row in enumerate(rows):
                for c,value in enumerate(row):self.audit_table.setItem(i,c,heavy_ui.make_item(value))
                self.audit_table.setRowHeight(i,38)
        finally:self.audit_table.setUpdatesEnabled(True)

    def refresh_backups(self):
        if not hasattr(self,'backup_combo') or not any(self.can(code) for code in (Permission.BACKUP_MANAGE,Permission.BACKUP_RESTORE,Permission.BACKUP_DELETE)):return
        from .desktop_live import drafts_folder
        folder=drafts_folder(self.workshop_manager.root,self.workshop).parent/'backups'/'manual'
        self._read_section('backups',lambda:[(p.name,str(p)) for p in sorted(folder.glob('*.db'),reverse=True)])

    def _apply_backups(self,rows):
        combo=self.backup_combo;previous=combo.currentData();combo.blockSignals(True);combo.clear()
        for name,path in rows:combo.addItem(name,path)
        combo.setCurrentIndex(max(0,combo.findData(previous)));combo.blockSignals(False)

    def _build_orders_tab(self):
        super()._build_orders_tab()
        from .ui_controls import OrderListView
        old=self.orders_table
        columns=[(str(i),old.horizontalHeaderItem(i).text()) for i in range(old.columnCount())]
        view=OrderListView(columns)
        view.horizontalHeader().setFixedHeight(50)
        view.setContextMenuPolicy(Qt.CustomContextMenu);view.customContextMenuRequested.connect(self._orders_context_menu)
        view.itemSelectionChanged.connect(self._order_selection_changed)
        view.itemDoubleClicked.connect(lambda *_:self._open_selected())
        old.parentWidget().layout().replaceWidget(old,view)
        old.hide();old.deleteLater();self.orders_table=view
        from .workspace_ui import EmptyTableMessage
        self.native_empty_orders=EmptyTableMessage(view,"Для начала работы создайте наряд.")

    def refresh_orders(self,*_):
        if not hasattr(self,"_live_signals") or self._live_closed:return
        if not self.can(Permission.ORDERS_VIEW):
            self._orders_pending=None;self.orders_table.report_model.set_rows([]);return
        self._orders_generation+=1
        shift=source_text(self.order_filter_shift)
        query={"start":self.order_filter_date.startDate().toString("yyyy-MM-dd"),"end":self.order_filter_date.endDate().toString("yyyy-MM-dd"),"master":self.order_filter_master.currentData(),"department":self.order_filter_dep.currentData(),"shift":None if shift=="Все смены" else shift}
        self._orders_pending=(self._orders_generation,query)
        self._start_orders_read()

    def _start_orders_read(self):
        if self._orders_running or self._orders_pending is None:return
        self._orders_running=True;generation,query=self._orders_pending;self._orders_pending=None
        db,root,key,signals=self.db,self.workshop_manager.root,self.workshop,self._live_signals
        drafts=local_drafts_dir()
        def worker():
            from .desktop_live import load_orders
            try:display=load_orders(db,root,key,drafts,query);error=""
            except Exception as exc:display=None;error=str(exc)
            try:signals.orders.emit(generation,display,error)
            except RuntimeError:pass
        threading.Thread(target=worker,name="SmartOrderOrdersRead",daemon=True).start()

    def _orders_loaded(self,generation,display,error):
        self._orders_running=False
        if self._live_closed:return
        if self._orders_pending is not None:self._start_orders_read();return
        if generation!=self._orders_generation:return
        if error:
            self.orders_table.setToolTip("Синхронизация временно недоступна: "+error);return
        self.orders_table.setToolTip("")
        if display==getattr(self,"_display_orders",None):return
        self._display_orders=display
        selected=self._selected_ref();scroll=self.orders_table.verticalScrollBar().value()
        self.orders_table.blockSignals(True);self.orders_table.setUpdatesEnabled(False)
        try:
            self.orders_table.report_model.set_rows(display)
            selection=next((i for i,rec in enumerate(display) if rec[0]==selected),-1)
            if selection>=0:self.orders_table.selectRow(selection)
            else:self.orders_table.setCurrentCell(-1,-1);self.orders_table.clearSelection()
            self.orders_table.verticalScrollBar().setValue(scroll)
        finally:self.orders_table.blockSignals(False);self.orders_table.setUpdatesEnabled(True)
        self._order_selection_changed()

    def _order_selection_changed(self):
        if not hasattr(self,"_live_signals"):return
        ref=self._selected_ref();draft=isinstance(ref,str) and ref.lower().endswith(".json")
        self.edit_order_btn.setEnabled(bool(ref) and self.can(Permission.ORDERS_EDIT))
        self.export_order_btn.setEnabled(isinstance(ref,int) and self.can(Permission.ORDERS_EXPORT))
        self.delete_draft_btn.setEnabled(draft and self.can(Permission.ORDERS_DELETE_DRAFT))
        self._history_generation+=1;generation=self._history_generation;self.info_users_list.clear()
        if draft:self.info_users_list.addItem("Общий черновик");return
        if not isinstance(ref,int) or not self.can(Permission.ORDERS_HISTORY):return
        db,signals=self.db,self._live_signals
        def worker():
            try:history=list(reversed(db.order_history(ref)));error=""
            except Exception as exc:history=[];error=str(exc)
            try:signals.history.emit(generation,history,error)
            except RuntimeError:pass
        threading.Thread(target=worker,name="SmartOrderHistoryRead",daemon=True).start()

    def _history_loaded(self,generation,history,error):
        if generation!=self._history_generation or self._live_closed:return
        self.info_users_list.clear()
        if error:self.info_users_list.addItem("История временно недоступна");return
        for index,rec in enumerate(history):
            who=rec['edited_by'] or 'Система';when=rec['edit_date'] or rec['registration_date']
            item=QListWidgetItem(("Создал" if index==0 else "Редактировал")+": "+who+(" · "+when if when else ""))
            item.setData(Qt.UserRole,rec);self.info_users_list.addItem(item)

    def _rc12_watch_tick(self):
        if not hasattr(self,"_live_signals") or self._live_closed or self._rc12_watch_running:return
        self._rc12_watch_running=True
        db,manager,key,signals=self.db,self.workshop_manager,self.workshop,self._live_signals
        analytics_visible=self.tabs.currentIndex()==4
        def worker():
            from .desktop_live import drafts_folder
            try:
                tokens={"production":db.change_token(),"identity":manager.auth.change_token()}
                try:tokens['drafts']=(drafts_folder(manager.root,key)/heavy_ui._RC12_DRAFT_REVISION).read_text(encoding='ascii')
                except OSError:tokens['drafts']=''
                if analytics_visible:
                    tokens['analytics']=tuple((k,b.change_token()) for k,b in manager._databases.items())
                    with manager.auth.read_conn() as conn:
                        tokens['session_heartbeat']=conn.execute('SELECT MAX(heartbeat_at) FROM app_sessions').fetchone()[0]
                error=""
                previous=self._live_tokens or {}
                if previous.get('production')!=tokens['production'] or time.monotonic()>=self._archive_retry_at:
                    self._archive_retry_at=time.monotonic()+30
                    manager.archive_publisher.request(key,db.backend)
            except Exception as exc:tokens=None;error=str(exc)
            try:signals.watch.emit(tokens,error)
            except RuntimeError:pass
        threading.Thread(target=worker,name="SmartOrderLiveSync",daemon=True).start()

    def _live_checked(self,tokens,error):
        self._rc12_watch_running=False
        if self._live_closed or error:return
        previous=self._live_tokens or {};self._live_tokens={**previous,**tokens}
        if previous.get('production')!=tokens['production']:
            self.db.invalidate_cache();self._rc12_dirty_tabs.update({0,1,2,3})
            if self.analytics and self.tabs.currentIndex()==4:self.analytics.reload()
        if previous.get('identity')!=tokens['identity']:
            self.workshop_manager.auth.invalidate_cache();self._rc12_dirty_tabs.add(3)
        if previous.get('drafts')!=tokens['drafts']:self._rc12_dirty_tabs.add(0)
        if 'analytics' in tokens and (previous.get('analytics')!=tokens['analytics'] or previous.get('session_heartbeat')!=tokens.get('session_heartbeat')) and self.analytics:
            self.analytics.reload()
        if QApplication.activeModalWidget() is None:self._rc12_refresh_active_if_dirty()

    def open_order_file(self,path):
        if self._file_loading:return
        self._file_loading=True
        manager,user,signals=self.workshop_manager,self.user,self._live_signals
        def worker():
            from .desktop_live import load_order_file
            try:result=load_order_file(manager,user,path);error=""
            except Exception as exc:result=None;error=str(exc)
            try:signals.order_file.emit(result,error)
            except RuntimeError:pass
        threading.Thread(target=worker,name="SmartOrderOpenFile",daemon=True).start()

    def _order_file_loaded(self,result,error):
        self._file_loading=False
        if self._live_closed:return
        if error:QMessageBox.warning(self,"Наряд",error);return
        db,order=result['db'],result['order']
        window=self._switch_to_workshop(db.workshop)
        if window is None:return
        def open_editor():
            token=None
            try:
                editable=result['live'] and result['latest'] and window.can(Permission.ORDERS_EDIT)
                if editable:
                    token,holder=db.acquire_edit_lock(order['info']['id'],window.user)
                    if token is None:editable=False
                dialog=heavy_ui.WorkOrderDialog(db,window.user,order,view_only=not editable,lock_token=token,parent=window)
                if not result['live']:
                    dialog.setWindowTitle("Копия наряда из файла · просмотр")
                if result.get('latest_order'):
                    latest_button=QPushButton("Открыть актуальную версию "+str(result['latest_order']['info']['version']),dialog)
                    dialog.layout().insertWidget(0,latest_button)
                    def open_latest():
                        dialog.reject()
                        QTimer.singleShot(0,lambda:window._order_file_loaded({**result,'order':result['latest_order'],'latest':True,'latest_order':None},''))
                    latest_button.clicked.connect(open_latest)
                if dialog.exec_()==QDialog.Accepted and editable:
                    data=dialog.get_data()
                    db.save_order(window.user,data['order_date'],data['shift_type'],data['master_id'],data['department_id'],data['lines'],data['comment'],parent_id=order['info']['id'],separate_worker=bool(data.get('separate_worker',False)))
                    dialog._delete_draft();window.refresh_orders()
                dialog.deleteLater()
            except Exception as exc:QMessageBox.warning(window,"Наряд",str(exc))
            finally:
                if token:
                    try:db.release_edit_lock(order['info']['id'],token)
                    except Exception:logging.exception("Не удалось освободить блокировку наряда")
        QTimer.singleShot(0,open_editor)

    def _build(self):
        self._enterprise_building=True
        super()._build()
        # Existing lazy pages use indexes 0..3; new pages are built by this class.
        self.tabs.insertTab(4,QWidget(),"Аналитика")
        self.tabs.insertTab(5,QWidget(),"Персонализация")
        for i,permission in [(0,Permission.ORDERS_VIEW),(1,Permission.CATALOG_VIEW),(2,Permission.EMPLOYEES_VIEW),(3,Permission.ADMIN_VIEW),(4,Permission.ANALYTICS_VIEW)]:self.tabs.setTabEnabled(i,self.can(permission))
        self.tabs.setTabEnabled(5,True);self.tabs.setTabEnabled(6,True);self._tab_motion=TabMotion(self.tabs.tabBar())
        layout=self.centralWidget().layout();layout.setContentsMargins(0,0,0,0);self.titlebar=TitleBar(self);layout.insertWidget(0,self.titlebar)
        self.zoom_message=QLabel('Во вкладке "Аналитика" Функция масштаба недоступна');self.zoom_message.setWordWrap(True);self.zoom_message.hide();layout.insertWidget(2,self.zoom_message)
        grip_row=QHBoxLayout();grip_row.setContentsMargins(0,0,0,0);grip_row.addStretch();self.grip=QSizeGrip(self);grip_row.addWidget(self.grip);layout.addLayout(grip_row)
        self.tabs.setCurrentIndex(0)
        self._analytics_order_overlay=None
        from .interaction_ui import install_access_cursor
        install_access_cursor()
        self._update_permission_controls()
        self._enterprise_building=False
        self.zoom.sliderReleased.connect(self._rc18_commit_zoom)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        overlay=getattr(self,"_analytics_order_overlay",None)
        if overlay is not None:
            overlay.setGeometry(overlay.parentWidget().rect());overlay.raise_()

    def _apply_native_titlebars(self):
        from .native_chrome import apply_frame
        apply_frame(self,self.ui_settings.theme=="dark")
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget,QDialog) and widget.isVisible():
                heavy_ui._rc14_force_windows_titlebar(widget,self.ui_settings.theme=="dark")

    def nativeEvent(self,event_type,message):
        from .native_chrome import native_event
        result=native_event(self,message)
        return result if result is not None else super().nativeEvent(event_type,message)

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.WindowStateChange and hasattr(self,"titlebar"):
            for button in self.titlebar.controls:button.update()

    def _replace_tab(self,index,widget,title):
        host=self.tabs.widget(index)
        widget.setParent(host,Qt.Widget);widget.setAttribute(Qt.WA_DontCreateNativeAncestors,True);widget.hide()
        from .liquid_effects import apply_liquid_surface
        from .workspace_ui import apply_page_scale
        from .i18n import apply_language
        apply_liquid_surface(widget,self.ui_settings.theme)
        apply_page_scale(widget,self.ui_settings.appearance,100 if index==4 else self.ui_settings.zoom)
        apply_language(widget,self.ui_settings.language)
        return super()._replace_tab(index,widget,tr(title))

    def _tab_changed(self,index):
        if getattr(self,"_building_tab",False) or getattr(self,"_enterprise_building",False):return
        if index not in self._loaded_tabs and index in range(1,7):
            builders={1:self._build_catalog_tab,2:self._build_employees_tab,3:self._build_admin_tab,4:lambda:AnalyticsWidget(self),5:self._build_personalization_tab,6:self._build_about_tab}
            titles={1:"Номенклатура",2:"Сотрудники",3:"Администрирование",4:"Аналитика",5:"Персонализация",6:"О приложении"}
            self._building_tab=True
            try:
                widget=builders[index]()
                if index==4:self.analytics=widget
                self._replace_tab(index,widget,titles[index]);self._loaded_tabs.add(index)
                if index==3:self.refresh_users();self.refresh_audit();self.refresh_backups()
            finally:self._building_tab=False
        if index==4 and self.analytics is not None and self.analytics.dark!=(self.ui_settings.theme=="dark"):self.analytics.set_theme(self.ui_settings.theme)
        self._update_zoom_mode();self._apply_current_page_scale()
        from .i18n import apply_language
        apply_language(self.tabs.currentWidget(),self.ui_settings.language)
        if index in getattr(self,"_rc12_dirty_tabs",set()):QTimer.singleShot(0,self._rc12_refresh_active_if_dirty)

    def _update_zoom_mode(self):
        if not hasattr(self,"zoom_message"):return
        from .i18n import tr
        analytics=self.tabs.currentIndex()==4;self._analytics_zoom_active=analytics
        self.zoom_message.setText(tr("В данной вкладке функция масштаба недоступна"));self.zoom_message.setVisible(analytics)
        self.zoom.setVisible(not analytics);self.zoom.setEnabled(not analytics);self.zoom_label.setVisible(not analytics)
        if hasattr(self,"scale_caption"):self.scale_caption.setVisible(not analytics)
        self.theme.setVisible(self.tabs.currentIndex()!=5);self.theme_caption.setVisible(self.tabs.currentIndex()!=5)
        for shortcut in getattr(self,"_rc18_shortcuts",[]):shortcut.setEnabled(not analytics)

    def _apply_zoom(self,value):
        value=max(50,min(200,int(value)))
        if getattr(self,"_analytics_zoom_active",False):
            old=self.zoom.blockSignals(True);self.zoom.setValue(self.ui_settings.zoom);self.zoom.blockSignals(old);return
        self.ui_settings.zoom=value
        if hasattr(self,"zoom_label"):self.zoom_label.setText(f"{value}%")
        timer=getattr(self,"_rc18_zoom_timer",None)
        if timer is not None:
            timer.stop()
            if not self.zoom.isSliderDown():timer.start(120)

    def _apply_current_page_scale(self):
        if not hasattr(self,"tabs"):return
        page=self.tabs.currentWidget()
        if page is None or (self.tabs.currentIndex()==0 and getattr(self,"_glass",None) is not None):return
        from .workspace_ui import apply_page_scale
        # Lazy tabs contain a mounted page. Update the same root that received
        # its initial typography so an older child stylesheet cannot win.
        content=page.layout().itemAt(0).widget() if page.layout() and page.layout().count() else None
        target=content if content is not None else page
        apply_page_scale(target,self.ui_settings.appearance,100 if self.tabs.currentIndex()==4 else self.ui_settings.zoom)
        page._page_scale_key=target._page_scale_key

    def _set_visual_zoom(self,value):self._apply_current_page_scale()

    def _rc18_commit_zoom(self):
        if getattr(self,"_analytics_zoom_active",False):return
        self._apply_current_page_scale();self._ensure_tab_widths()
        if getattr(self,"_last_saved_zoom",None)!=self.ui_settings.zoom:
            self.settings_store.save(self.ui_settings);self._last_saved_zoom=self.ui_settings.zoom
        if hasattr(self,"_schedule_glass_state"):self._schedule_glass_state()

    def _theme_toggled(self,checked):
        theme = "dark" if checked else "light"
        motion = getattr(self, "_window_motion", None)
        if (theme != self.ui_settings.theme and self.isVisible()
                and not getattr(self, "_scheduled_change", False)
                and (motion is None or motion.animation is None)):
            toggle = self.theme
            panel = getattr(self, "appearance_panel", None)
            if not toggle.isVisible() and panel is not None:
                toggle = panel.theme_toggle
            if toggle.isVisible():
                shell = self.centralWidget()
                self._theme_frame = (shell.grab(), toggle.mapTo(shell, toggle.rect().center()))
        if self.ui_settings.auto_theme and not getattr(self,"_scheduled_change",False):self.ui_settings.auto_theme=False
        self.ui_settings.theme = theme
        self.theme_caption.setText(tr("Тёмная тема" if checked else "Светлая тема"))
        self._sync_personalization_controls()
        if not hasattr(self,"_theme_apply_timer"):
            self._theme_apply_timer=QTimer(self);self._theme_apply_timer.setSingleShot(True);self._theme_apply_timer.timeout.connect(self._finish_theme_change)
        self._theme_apply_timer.start(0)

    def _finish_theme_change(self):
        frame = getattr(self, "_theme_frame", None)
        self._theme_frame = None
        self._apply_theme();self.settings_store.save(self.ui_settings)
        self._update_zoom_mode()
        if hasattr(self,"_schedule_glass_state"):self._schedule_glass_state()
        if frame is not None:
            from .liquid_effects import transition_to
            snapshot, origin = frame
            effect = transition_to(self.centralWidget(), snapshot, origin=origin, hold=True)
            if effect is not None:
                web = getattr(self, "_glass", None)
                web_visible = web is not None and web.isVisible() and self._glass_ready
                if web_visible:
                    self._publish_glass_state()
                # Let Chromium receive the new palette before revealing it.
                effect.fade(.30, delay=.045 if web_visible else 0)

    def _apply_theme(self):
        from .heavy_styles import apply_apple_design
        apply_apple_design(self,self.ui_settings.theme,self.ui_settings.zoom)
        if hasattr(self,"titlebar"):self.titlebar.set_theme(self.ui_settings.theme)
        self._apply_admin_filter_theme();self._apply_native_titlebars()
        if self.analytics is not None and self.analytics.isVisible():self.analytics.set_theme(self.ui_settings.theme)

    def toggle_window_mode(self,fullscreen=True):
        from .interaction_ui import WindowMotion
        if not hasattr(self,"_window_motion"):self._window_motion=WindowMotion(self)
        self._window_motion.toggle(fullscreen)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Escape,Qt.Key_F11):
            if not event.isAutoRepeat():self.toggle_window_mode(True)
            event.accept();return
        super().keyPressEvent(event)

    def _orders_top_restricted(self):
        return not any(self.can(code) for code in (Permission.ORDERS_CREATE,Permission.ORDERS_EDIT,Permission.ORDERS_EXPORT,Permission.ORDERS_FILTER,Permission.ORDERS_HISTORY,Permission.ORDERS_DELETE_DRAFT))

    def _refresh_visible_tab(self):
        from PyQt5 import sip
        if not sip.isdeleted(self) and not getattr(self,"_live_closed",False):self._tab_changed(self.tabs.currentIndex())

    def _reference_permissions(self,prefix):
        stem="work" if prefix=="catalog" else "person"
        table=getattr(self,stem+"_table",None) if prefix=="catalog" else getattr(self,"people_table",None)
        recent=getattr(self,"_show_recent_deleted_work" if prefix=="catalog" else "_show_recent_deleted_people",False)
        selected=table is not None and table.currentRow()>=0 and not recent
        for kind in ("edit","save","delete"):
            button=getattr(self,stem+"_"+kind+"_btn",None)
            if button is not None:
                code=prefix+(".delete" if kind=="delete" else ".edit")
                button.setProperty("requiredPermission",code)
                button.setEnabled(self.can(code) and (button.isEnabled() if kind=="save" else selected))
        for name in (("work_name","work_code","work_price") if prefix=="catalog" else ("person_name",)):
            widget=getattr(self,name,None)
            if widget is not None:widget.setEnabled(self.can(prefix+".create") or self.can(prefix+".edit"))

    def _heavy_work_selection(self):
        super()._heavy_work_selection();self._reference_permissions("catalog")

    def _heavy_people_selection(self):
        super()._heavy_people_selection();self._reference_permissions("employees")

    def _open_selected(self):
        if not self.can(Permission.ORDERS_VIEW):return
        ref=self._selected_ref()
        if isinstance(ref,int) and not self.can(Permission.ORDERS_EDIT):
            self.open_notification_order({"workshop_key":self.workshop,"order_id":ref});return
        return super()._open_selected()

    def export_order(self):
        try:
            self.workshop_manager.require(self.user,Permission.ORDERS_EXPORT)
            return super().export_order()
        except Exception as exc:QMessageBox.warning(self,tr("Недоступно"),str(exc))

    def _orders_context_menu(self,pos):
        item=self.orders_table.itemAt(pos)
        if item is None:return
        self.orders_table.selectRow(item.row());ref=self._selected_ref();menu=QMenu(self)
        entries=[("Просмотреть наряд",Permission.ORDERS_VIEW,self._open_selected,ref is not None),
            ("Редактировать",Permission.ORDERS_EDIT,self.edit_order,ref is not None),
            ("Выгрузить в Excel",Permission.ORDERS_EXPORT,self.export_order,isinstance(ref,int)),
            ("Удалить черновик",Permission.ORDERS_DELETE_DRAFT,self.delete_selected_draft,isinstance(ref,str)),
            ("ИСТОРИЯ РЕДАКТИРОВАНИЙ",Permission.ORDERS_HISTORY,self._show_history_details,isinstance(ref,int))]
        actions={}
        for title,code,callback,selected in entries:
            action=menu.addAction(tr(title));action.setEnabled(selected and self.can(code));actions[action]=(code,callback)
        result=menu.exec_(self.orders_table.viewport().mapToGlobal(pos))
        if result in actions:
            code,callback=actions[result]
            try:self.workshop_manager.require(self.user,code);callback()
            except Exception as exc:QMessageBox.warning(self,tr("Недоступно"),str(exc))

    def _update_permission_controls(self):
        if not hasattr(self,"tabs"):return
        from .interaction_ui import RestrictedArea
        previous=self.tabs.currentIndex();blocked=self.tabs.blockSignals(True)
        for index,permission in enumerate((Permission.ORDERS_VIEW,Permission.CATALOG_VIEW,Permission.EMPLOYEES_VIEW,Permission.ADMIN_VIEW,Permission.ANALYTICS_VIEW)):
            self.tabs.setTabEnabled(index,self.can(permission))
        target=previous if self.tabs.isTabEnabled(previous) else next(i for i in range(self.tabs.count()) if self.tabs.isTabEnabled(i))
        self.tabs.setCurrentIndex(target);self.tabs.blockSignals(blocked)
        if target!=previous:
            if hasattr(self,"_live_signals") and not getattr(self,"_enterprise_building",False):self._tab_changed(target)
            else:QTimer.singleShot(0,self._refresh_visible_tab)
        if hasattr(self,"create_order_btn"):
            self.create_order_btn.setEnabled(self.can(Permission.ORDERS_CREATE))
            self.delete_draft_btn.setVisible(True);self.info_panel.setVisible(True)
            for widget in (self.order_filter_date,self.order_filter_master,self.order_filter_shift,self.order_filter_dep):widget.setEnabled(self.can(Permission.ORDERS_FILTER))
            self.info_panel.setProperty("accessDenied",not self.can(Permission.ORDERS_HISTORY));self.info_panel.setCursor(Qt.ArrowCursor if self.can(Permission.ORDERS_HISTORY) else Qt.ForbiddenCursor)
            restricted=self._orders_top_restricted()
            overlay=getattr(self,"_analytics_order_overlay",None)
            if restricted and overlay is None:
                overlay=RestrictedArea(self.tabs.widget(0),[self.order_filter_date,self.create_order_btn.parentWidget(),self.info_panel]);self._analytics_order_overlay=overlay
            if overlay is not None:overlay.setVisible(restricted)
        if hasattr(self,"titlebar"):
            self.titlebar.bell.setVisible(self.can(Permission.NOTIFICATIONS_VIEW));self.titlebar.badge.setEnabled(getattr(self,"_account_active",True))
        if hasattr(self,"_notification_timer"):
            if self.can(Permission.NOTIFICATIONS_VIEW):self._notification_timer.start()
            else:
                self._notification_timer.stop()
                if self.notification_popup is not None:self.notification_popup.close()
        if hasattr(self,"users_table"):
            for index in range(self.users_table.rowCount()):
                cell=self.users_table.cellWidget(index,3)
                if cell is not None:
                    permitted=self.can(Permission.USERS_MANAGE) and (self.can(Permission.PERMISSIONS_MANAGE) or set(cell.property("targetPermissions") or [])<=set(self.user.permissions))
                    for button in cell.findChildren(QPushButton):button.setEnabled(permitted and bool(cell.property("hasManagementHandlers")))

    def add_user(self):
        if not self.can(Permission.USERS_MANAGE):return
        from .account_ui import AccountDialog
        dialog=AccountDialog(parent=self)
        if dialog.exec_()!=QDialog.Accepted:return
        try:
            self.db.add_user(self.user,dialog.username.text(),dialog.password.text(),dialog.selected_roles(),**dialog.account_options());self._visible_users=None;self.refresh_users()
        except Exception as exc:QMessageBox.warning(self,tr("Пользователь"),str(exc))
        finally:dialog.deleteLater()

    def _edit_user_by_id(self,uid,username,role):
        if not self.can(Permission.USERS_MANAGE):return
        from .account_ui import AccountDialog
        from .account_store import UNSET
        dialog=AccountDialog(username,role,False,self,options=self.workshop_manager.auth.user_options(uid))
        if dialog.exec_()!=QDialog.Accepted:return
        try:
            options=dialog.account_options()
            if not self.can(Permission.PERMISSIONS_MANAGE):options["permissions"]=UNSET
            self.db.update_user(self.user,uid,dialog.username.text(),dialog.selected_roles(),dialog.password.text(),**options)
            if uid==self.user.id:
                prior_store=self.settings_store
                self.user=SessionUser(uid,dialog.username.text().strip(),dialog.selected_roles(),self.workshop_manager.auth.permissions_for_user(uid,dialog.selected_roles()))
                from .config import SettingsStore
                self.settings_store=SettingsStore(uid,self.user.username);self.settings_store.on_save=prior_store.on_save;self.settings_store.save(self.ui_settings)
                self.db.user=self.user;self.session_tracker.user=self.user;self._update_permission_controls()
                self.titlebar.badge.setText(f"{self.user.username}  ·  {tr(WORKSHOPS[self.workshop])}  ▾")
            self._visible_users=None;self.refresh_users()
        except Exception as exc:QMessageBox.warning(self,tr("Пользователь"),str(exc))
        finally:dialog.deleteLater()

    def _sync_personalization_controls(self):
        panel = getattr(self, "appearance_panel", None)
        if panel is None: return
        for control, value in [(panel.theme_toggle, self.ui_settings.theme == "dark"),
                               (panel.auto_theme, self.ui_settings.auto_theme),
                               (panel.remember, self.ui_settings.remember_personalization)]:
            previous = control.blockSignals(True)
            control.setChecked(value); control.blockSignals(previous)
        panel.theme_label.setText(tr("Тёмная тема" if self.ui_settings.theme == "dark" else "Светлая тема"))

    def set_config_sync(self,enabled):
        if self.user.id<=0:return
        self.ui_settings.sync_personalization=bool(enabled);self.settings_store.save(self.ui_settings)

    def share_personalization(self):
        from .profile_sync import export_current_config
        try:
            path=export_current_config(self.user,self.ui_settings)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
            if getattr(self,"appearance_panel",None) is not None:self.appearance_panel.sync_status.setText(tr("Конфиг сохранён: ")+path.name)
            return path
        except Exception as exc:QMessageBox.warning(self,tr("Персонализация"),str(exc))

    def import_personalization(self):
        from pathlib import Path
        import json
        from dataclasses import fields
        from .config import UiSettings
        from .profile_sync import read_config
        from .i18n import set_language
        from PyQt5.QtWidgets import QFileDialog
        path,_=QFileDialog.getOpenFileName(self,tr("Загрузить конфиг…"),"","SmartOrder (*.json)")
        if not path:return
        try:
            source=Path(path)
            if source.stat().st_size>8*1024*1024:raise ValueError("Конфигурация слишком велика: максимум 8 МБ")
            loaded=read_config(json.loads(source.read_text(encoding="utf-8")))
            loaded.sync_personalization=self.ui_settings.sync_personalization
            previous_about=self.ui_settings.about_theme
            for field in fields(UiSettings):setattr(self.ui_settings,field.name,getattr(loaded,field.name))
            set_language(loaded.language)
            blocked=self.theme.blockSignals(True);self.theme.setChecked(loaded.theme=="dark");self.theme.blockSignals(blocked)
            self.theme_caption.setText(tr("Тёмная тема" if loaded.theme=="dark" else "Светлая тема"))
            self.set_appearance(loaded.appearance);self.set_language(loaded.language)
            if 5 in self._loaded_tabs:self._replace_tab(5,self._build_personalization_tab(),"Персонализация")
            if previous_about!=loaded.about_theme and 6 in self._loaded_tabs:self._replace_tab(6,self._build_about_tab(),"О приложении")
            self._update_zoom_mode();self._apply_current_page_scale()
            old=self.zoom.blockSignals(True);self.zoom.setValue(loaded.zoom);self.zoom.blockSignals(old);self.zoom_label.setText(str(loaded.zoom)+"%")
            self.settings_store.save(self.ui_settings)
            return loaded
        except Exception as exc:QMessageBox.warning(self,tr("Персонализация"),str(exc))

    def set_remember_personalization(self, remember):
        self.settings_store.set_startup_enabled(self.ui_settings,remember)

    def set_language(self,code):
        from .i18n import LANGUAGES
        if code not in LANGUAGES:return
        self.ui_settings.language=code
        from .i18n import set_language,apply_language
        set_language(code);apply_language(self,code)
        self.titlebar.badge.setText(f"{self.user.username}  ·  {tr(WORKSHOPS[self.workshop])}  ▾")
        from .workspace_ui import align_action_sizes,EmptyTableMessage
        for index in (1,2):
            if index in self._loaded_tabs:align_action_sizes(self.tabs.widget(index),self.ui_settings.appearance,self.ui_settings.zoom)
        for message in self.findChildren(EmptyTableMessage):message.refresh()
        self._update_session_labels();self._update_zoom_mode();self._ensure_tab_widths();self.settings_store.save(self.ui_settings)
        if hasattr(self,"_schedule_glass_state"):self._schedule_glass_state()

    def set_auto_theme(self, enabled):
        self.ui_settings.auto_theme = bool(enabled)
        self._apply_scheduled_theme()
        self.settings_store.save(self.ui_settings)
        self._sync_personalization_controls()

    def _apply_scheduled_theme(self, now=None):
        if not self.ui_settings.auto_theme: return
        from .config import scheduled_theme
        checked = scheduled_theme(now) == "dark"
        if self.theme.isChecked() != checked:
            self._scheduled_change = True
            try: self.theme.setChecked(checked)
            finally: self._scheduled_change = False

    def _build_personalization_tab(self):
        from .appearance_ui import AppearancePanel
        page = QWidget(self.tabs)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(page)
        scroll.setWidgetResizable(True)
        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 12)
        self.appearance_panel = AppearancePanel(self)
        layout.addWidget(self.appearance_panel)
        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.personalization_session_label = QLabel(self._session_text())
        self.personalization_session_label.setObjectName("SessionLabel")
        self.personalization_session_label.setAlignment(Qt.AlignRight)
        root.addWidget(self.personalization_session_label)
        return page

    def set_personalization(self, appearance, about_theme):
        changed = self.ui_settings.about_theme != about_theme
        self.ui_settings.about_theme = 1 if about_theme == 1 else 2
        self.set_appearance(appearance)
        if changed and 6 in self._loaded_tabs:
            self._replace_tab(6, self._build_about_tab(), "О приложении")

    def _sync_current_tab(self):
        if hasattr(self,"tabs") and self.tabs.currentIndex()==4:
            if self.analytics:self.analytics.reload()
            return
        return super()._sync_current_tab()

    def _align_reference_actions(self,tab,people=False):
        content=tab.widget() if isinstance(tab,QScrollArea) else tab
        layout=content.layout()
        add=next(b for b in content.findChildren(QPushButton) if b.text()=="Добавить")
        imp=next(b for b in content.findChildren(QPushButton) if b.text()=="Загрузить из Excel")
        def detach(parent,widget):
            parent.removeWidget(widget)
            for i in range(parent.count()):
                child=parent.itemAt(i).layout()
                if child is not None:detach(child,widget)
        for button in (add,imp):detach(layout,button)
        if people:
            top=layout.itemAt(0).layout()
            detach(layout,self.recent_deleted_btn)
            form=layout.itemAt(1).layout();form.addWidget(self.recent_deleted_btn)
        else:
            top=QHBoxLayout();top.addStretch();layout.insertLayout(0,top)
        for button,kind in [(add,"add"),(imp,"import")]:
            button.setProperty("alignedAction",kind);button.setVisible(True)
            button.setEnabled(self.can(("employees" if people else "catalog")+(".create" if kind=="add" else ".import")));top.addWidget(button)
        self._reference_permissions("employees" if people else "catalog")
        content.setProperty("referencePage",True)
        from .workspace_ui import align_action_sizes
        align_action_sizes(content,self.ui_settings.appearance,self.ui_settings.zoom)
        # Keep wide forms scrollable rather than enlarging the main window.
        scroll=QScrollArea(self.tabs);scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);scroll.setWidget(content)
        return scroll

    def _build_catalog_tab(self):
        tab=super()._build_catalog_tab()
        from .workspace_ui import EmptyTableMessage
        self.work_empty=EmptyTableMessage(self.work_table,"Для начала работы добавьте номенклатуру или загрузите её из Excel.",self.work_search)
        return self._align_reference_actions(tab)

    def _build_employees_tab(self):
        tab=super()._build_employees_tab()
        from .workspace_ui import EmptyTableMessage
        self.people_empty=EmptyTableMessage(self.people_table,"Для начала работы добавьте сотрудников или загрузите их из Excel.",self.person_search)
        return self._align_reference_actions(tab,True)

    def refresh_people(self):
        super().refresh_people()
        from .i18n import apply_widget
        for name in ("person_form_label","person_name","person_search","people_results_label"):
            widget=getattr(self,name,None)
            if widget is not None:widget._i18n_language=None;apply_widget(widget)

    def _build_admin_tab(self):
        actual=self.user
        self.user=SessionUser(actual.id,actual.username,"Администратор",frozenset(ALL_PERMISSIONS))
        try:tab=super()._build_admin_tab()
        finally:self.user=actual
        content=tab.widget() if isinstance(tab,QScrollArea) else tab
        from PyQt5.QtWidgets import QGroupBox
        for group in content.findChildren(QGroupBox):
            if "Резервное копирование" in group.title():
                group.setTitle("▣ Резервное копирование и архивы")
        for button in content.findChildren(QPushButton):
            if "Создать бэкап" in button.text():
                button.setText("Создать бэкап"); button.setProperty("symbolIcon", "backup")
                button.setIcon(symbol_icon("backup", self.ui_settings.theme))
            elif "Восстановить" in button.text():
                button.setText("Восстановить"); button.setProperty("symbolIcon", "restore")
                button.setIcon(symbol_icon("restore", self.ui_settings.theme))
        self._admin_filter_labels=[]
        for label in content.findChildren(QLabel):
            if label.text() in ("Период:","Пользователь:"):
                label.setObjectName("AuditFilterLabel")
                self._admin_filter_labels.append(label)
        self._apply_admin_filter_theme()
        label=QLabel("Общие учётные записи и сессии: "+str(self.workshop_manager.auth.path));label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextSelectableByMouse);content.layout().addWidget(label)
        b=QPushButton("Резервная копия учётных записей и сессий");b.setObjectName("IdentityBackupButton");b.setProperty("requiredPermission",Permission.IDENTITY_BACKUP);b.clicked.connect(self.backup_identity);b.setEnabled(self.can(Permission.IDENTITY_BACKUP));content.layout().addWidget(b)
        self._apply_admin_permissions(content)
        return tab

    def _apply_admin_permissions(self,content):
        checks={"Синхронизация":Permission.DATA_SYNC,"⟳  Синхронизация":Permission.DATA_SYNC,"Архивный снимок":Permission.BACKUP_MANAGE,"Открыть архивные снимки":Permission.BACKUP_MANAGE,"Собрать логи":Permission.AUDIT_VIEW,"↶ Восстановить":Permission.BACKUP_RESTORE,"Добавить пользователя":Permission.USERS_MANAGE,"Разрешительный режим":Permission.ACCESS_CONTROL,"Создать бэкап":Permission.BACKUP_MANAGE,"Восстановить":Permission.BACKUP_RESTORE,"Удалить":Permission.BACKUP_DELETE,"Создать архивный снимок":Permission.BACKUP_MANAGE,"Открыть архивный снимок":Permission.BACKUP_MANAGE,"Создать лог":Permission.AUDIT_VIEW,"Центр диагностики":Permission.DIAGNOSTICS_VIEW,"Обновить патч":Permission.APP_UPDATE,"Синхронизировать":Permission.DATA_SYNC}
        from PyQt5.QtWidgets import QAbstractButton,QGroupBox
        for button in content.findChildren(QAbstractButton):
            from .i18n import REVERSE
            code=button.property("requiredPermission") or checks.get(REVERSE.get(button.text(),button.text()))
            if code:button.setEnabled(self.can(code));button.setProperty("requiredPermission",code)
        for name,code in (("access_control_check",Permission.ACCESS_CONTROL),("admin_sync_btn",Permission.DATA_SYNC),("diagnostics_center_btn",Permission.DIAGNOSTICS_VIEW),("update_patch_btn",Permission.APP_UPDATE)):
            widget=getattr(self,name,None)
            if widget is not None:widget.setEnabled(self.can(code))
        for name,code in (("users_table",Permission.USERS_VIEW),("audit_table",Permission.AUDIT_VIEW)):
            widget=getattr(self,name,None)
            if widget is not None:
                allowed=self.can(code) or code==Permission.USERS_VIEW and self.can(Permission.USERS_MANAGE)
                widget.setEnabled(allowed);group=widget.parentWidget()
                while group is not None and not isinstance(group,QGroupBox):group=group.parentWidget()
                if group is not None:group.setEnabled(allowed)
        if hasattr(self,"backup_combo"):self.backup_combo.setEnabled(any(self.can(code) for code in (Permission.BACKUP_MANAGE,Permission.BACKUP_RESTORE,Permission.BACKUP_DELETE)))

    def _apply_admin_filter_theme(self):
        labels=getattr(self,"_admin_filter_labels",())
        dark=self.ui_settings.theme=="dark"
        from .liquid_style import colors
        c = colors(dark)
        css=f"background:{c['field']};color:{c['ink']};border:1px solid {c['line']};"
        css += "padding:4px 7px;border-radius:4px;"
        for label in labels:
            label.setStyleSheet("QLabel{"+css+"}QLabel:disabled{color:"+c['disabled']+";}")

    def set_appearance(self, appearance):
        from .appearance_config import normalize_appearance
        self.ui_settings.appearance = normalize_appearance(appearance)
        self.settings_store.save(self.ui_settings)
        self._apply_theme()
        self._apply_current_page_scale()
        fonts = self.ui_settings.appearance["fonts"]
        self.titlebar.setFixedHeight(max(47, round(max(fonts["window_title"]["size"], fonts["caption"]["size"])) + 20))
        self._ensure_tab_widths()
        self.update()

    def create_backup(self):
        try:
            self.workshop_manager.require(self.user,Permission.BACKUP_MANAGE)
            return super().create_backup()
        except Exception as exc:QMessageBox.warning(self,tr("Недоступно"),str(exc))

    def delete_backup(self):
        try:
            self.workshop_manager.require(self.user,Permission.BACKUP_DELETE)
            return super().delete_backup()
        except Exception as exc:QMessageBox.warning(self,tr("Недоступно"),str(exc))

    def open_archive_snapshots(self):
        try:
            self.workshop_manager.require(self.user,Permission.BACKUP_MANAGE)
            return super().open_archive_snapshots()
        except Exception as exc:QMessageBox.warning(self,tr("Недоступно"),str(exc))

    def create_archive_snapshot(self):
        try:
            self.workshop_manager.require(self.user,Permission.BACKUP_MANAGE)
            return super().create_archive_snapshot()
        except Exception as exc:QMessageBox.warning(self,tr("Недоступно"),str(exc))

    def backup_identity(self):
        try:
            self.workshop_manager.require(self.user,Permission.IDENTITY_BACKUP)
            folder=network_root()/"backups"/"identity";folder.mkdir(parents=True,exist_ok=True)
            target=folder/("identity_"+datetime.now().strftime("%Y-%m-%d_%H-%M-%S")+".db")
            self.workshop_manager.auth.backup_to(target)
            QMessageBox.information(self,"Резервная копия","Учётные записи и сессии сохранены:\n"+str(target))
        except Exception as exc:QMessageBox.warning(self,"Резервная копия",str(exc))

    def choose_workshop(self):
        if getattr(self,"workshop_menu",None) is not None and self.workshop_menu.isVisible():self.workshop_menu.close();return
        from .interaction_ui import WorkshopPopup
        self.workshop_menu=WorkshopPopup(self)
        self.workshop_menu.popup(self.titlebar.badge.mapToGlobal(self.titlebar.badge.rect().bottomLeft())+QPointF(0,4).toPoint())

    def _switch_to_workshop(self,key):
        if key==self.workshop or getattr(self,"_workshop_switching",False) or key not in allowed_workshops(self.user):return self
        from .workspace_ui import WorkshopLoadingDialog
        QApplication.instance()._smartorder_main_window=self
        self._workshop_switching=True;self._workshop_loading=WorkshopLoadingDialog(key,self);self._workshop_loading.show();self.titlebar.badge.setEnabled(False)
        manager,user=self.workshop_manager,self.user
        def prepare():
            try:
                db=manager.database(key,user);db.get_employees(True);db.get_departments();self.session_tracker.switch(key)
                return key,db,""
            except Exception as exc:return key,None,str(exc)
        self._read_section("workshop_switch",prepare)
        return self

    def _apply_workshop_switch(self,result):
        key,db,error=result;loading=self._workshop_loading;self._workshop_switching=False;self.titlebar.badge.setEnabled(getattr(self,"_account_active",True))
        if error:
            loading.close();loading.deleteLater();QMessageBox.warning(self,"Цех",error);return
        self._orders_generation+=1;self._history_generation+=1
        self.db=db;self.workshop=key;set_active_workshop(key);self._display_orders=None;self._live_tokens=None
        self.orders_table.report_model.set_rows([]);self._rc12_dirty_tabs.update({0,1,2,3})
        from .i18n import tr
        self.titlebar.badge.setText(f"{self.user.username}  ·  {tr(WORKSHOPS[key])}  ▾")
        self._refresh_reference_filters();self.tabs.setCurrentIndex(0);self.refresh_orders()
        try:(local_state_dir()/f"workshop_{self.user.id}.txt").write_text(key)
        except OSError:pass
        if hasattr(self,"_schedule_glass_state"):self._schedule_glass_state()
        if self.analytics is not None:self.analytics.reload()
        self._workshop_loading_timer=QTimer(self);self._workshop_loading_timer.setInterval(30)
        def finish():
            if self._orders_running or self._orders_pending is not None:return
            self._workshop_loading_timer.stop();loading.close();loading.deleteLater()
        self._workshop_loading_timer.timeout.connect(finish);self._workshop_loading_timer.start()

    def open_diagnostics_center(self):
        from .live_ui import LiveDiagnosticsDialog
        dialog=LiveDiagnosticsDialog(self);dialog.setWindowState(dialog.windowState()|Qt.WindowMaximized);dialog.exec_()

    def refresh_notifications(self):
        if self._notification_loading:return
        self._notification_loading=True
        from .live_ui import notifications,unread_count
        def worker():
            try:
                workshop_access=self.can(Permission.NOTIFICATIONS_VIEW)
                items=notifications(self.workshop_manager,self.user) if workshop_access else []
                count=unread_count(self.workshop_manager,self.user) if workshop_access else 0
                notice=read_update_announcement()
                if notice:
                    message=(notice.get("title") or "Обновление SmartOrder")
                    if notice.get("description"):message += "\n" + notice["description"]
                    items.insert(0,{"id":-1,"read_at":None,"workshop_key":self.workshop,"created_at":notice.get("created_at") or "", "version":notice["version"],"message":message})
                error=""
            except Exception as exc:items=[];count=0;error=str(exc)
            try:self._notification_signals.loaded.emit(items,count,error)
            except RuntimeError:pass
        threading.Thread(target=worker,name="SmartOrderNotifications",daemon=True).start()

    def _notifications_loaded(self,items,count,error):
        self._notification_loading=False
        if not error:
            self._notification_items=items;self._notification_count=count
            self.titlebar.bell.setText("🔔"+(f" {count}" if count else ""))
            self.titlebar.bell.setStyleSheet("QPushButton{border:1px solid "+("#ED71A7" if count else "#738097")+";border-radius:10px;padding:4px 10px;min-height:22px;font-size:14px;}QPushButton:hover{border-color:#16B9B0;}QPushButton:pressed{background:#263B55;}")
        self.titlebar.bell.setToolTip("Не удалось обновить уведомления: "+error if error else f"Непрочитанных уведомлений: {count}")
        if self.notification_popup and self.notification_popup.isVisible():self.notification_popup.render(items,error)

    def show_notifications(self):
        if not self.can(Permission.NOTIFICATIONS_VIEW):return
        from .live_ui import NotificationPopup
        if self.notification_popup is not None:self.notification_popup.close();self.notification_popup.deleteLater()
        self.notification_popup=NotificationPopup(self)
        point=self.titlebar.bell.mapToGlobal(self.titlebar.bell.rect().bottomRight())
        screen=QApplication.screenAt(point) or QApplication.primaryScreen();bounds=screen.availableGeometry()
        x=max(bounds.left(),min(point.x()-460,bounds.right()-460));y=min(point.y()+6,bounds.bottom()-450)
        self.notification_popup.move(x,y);self.notification_popup.show();self.refresh_notifications()

    def open_notification_order(self,notice):
        self.workshop_manager.require(self.user,Permission.ORDERS_VIEW)
        window=self._switch_to_workshop(notice["workshop_key"])
        if window is None:return
        def show():
            try:
                order=window.db.get_order(int(notice["order_id"]))
                if order is None:raise RuntimeError("Версия наряда уже удалена политикой хранения или восстановлением базы.")
                dialog=heavy_ui.WorkOrderDialog(window.db,window.user,order,view_only=True,parent=window);dialog.exec_()
            except Exception as exc:QMessageBox.warning(window,"Наряд",str(exc))
        QTimer.singleShot(100,show)

    def _heartbeat(self):
        if self._heartbeat_running:return
        self._heartbeat_running=True
        def worker():
            try:self.session_tracker.heartbeat()
            except Exception:logging.exception("Не удалось записать heartbeat SmartOrder")
            finally:self._heartbeat_running=False
        threading.Thread(target=worker,name="SmartOrderSession",daemon=True).start()

    def closeEvent(self,event):
        super().closeEvent(event)
        if event.isAccepted():
            self._live_closed=True
            if hasattr(self,"_session_timer"):self._session_timer.stop()
            if hasattr(self,"_telemetry_timer"):self._telemetry_timer.stop()
            if hasattr(self,"_notification_timer"):self._notification_timer.stop()
            if self.notification_popup:self.notification_popup.close()
            if hasattr(self,"_db_ping_timer"):self._db_ping_timer.stop()
            if self.analytics:self.analytics.timer.stop();self.analytics.reload_timer.stop();self.analytics.filter_timer.stop()
            if not self._switching:
                try:self.session_tracker.heartbeat(close=True)
                except Exception:logging.exception("Не удалось закрыть сеанс SmartOrder")
        else:
            if hasattr(self,"_rc12_watch_timer"):self._rc12_watch_timer.start()

    def show_news(self, notice=None):
        from .news_ui import NewsDialog
        prefix=""
        if isinstance(notice,dict):
            version=str(notice.get("version","")).strip()
            message=str(notice.get("message","")).strip()
            if version:prefix="Обновление V "+version+(("\n"+message) if message else "")
        dialog=NewsDialog(self,network_root()/"UPDATE_NEWS.txt",prefix=prefix)
        dialog.exec_()

    def _about_browser(self,html,link_handler=None):
        browser=super()._about_browser(html,link_handler)
        browser.setProperty("largeAboutText",True)
        font=QFont("Segoe UI",14);browser.document().setDefaultFont(font)
        browser.setStyleSheet(browser.styleSheet()+" QTextBrowser{font-size:18px;} a{text-decoration:underline;}")
        return browser

    def _build_about_tab(self):
        if self.ui_settings.about_theme == 1:
            page = RC18MainWindow._build_about_tab(self)
            page.setProperty("legacyAppearance", True)
            return page
        from .glass_about import build_about_page
        return build_about_page(self)

    def _open_guide(self):
        from .policy import ensure_user_guide_document
        path=ensure_user_guide_document()
        if path:QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

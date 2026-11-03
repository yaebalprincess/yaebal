from __future__ import annotations

import threading
from PyQt5.QtCore import Qt,QTimer,pyqtSignal,QObject
from PyQt5.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QScrollArea,QWidget,QMessageBox
from .heavy_ui import DiagnosticsCenterDialog
from .analytics_ui import table,fill_table
from .security import Permission,WORKSHOP_ROLES,split_roles
from .workshops import allowed_workshops
from .db import now_text


class LiveDiagnosticsDialog(DiagnosticsCenterDialog):
    def _build_ui(self):
        super()._build_ui()
        self.active_label=QLabel("Открытые сеансы: загрузка…")
        self.layout().insertWidget(2,self.active_label)
        self.active_table=table([("username","Пользователь"),("role","Роль"),("computer","Компьютер"),("workshop_name","Цех"),("started_at","Вход, UTC"),("heartbeat_at","Последняя связь, UTC"),("duration_seconds","Время сеанса"),("client_path","Локальный клиент")]);self.active_table.setMinimumHeight(150);self.active_table.setMaximumHeight(230)
        self.layout().insertWidget(3,self.active_table)
    def _probe_worker(self,deep,quick):
        try:self._active_snapshot=(self.owner.workshop_manager.active_sessions(self.owner.user),"")
        except Exception as exc:self._active_snapshot=([],str(exc))
        super()._probe_worker(deep,quick)
    def _apply_sample(self,data):
        super()._apply_sample(data)
        rows,error=getattr(self,"_active_snapshot",([],""))
        if error:self.active_label.setText("Список сеансов недоступен: "+error)
        else:self.active_label.setText(f"Открыто экземпляров: {len(rows)} · пользователей: {len({r['user_id'] for r in rows})} · связь за последние 150 сек · обновление каждые 2 сек")
        fill_table(self.active_table,rows)


def notifications(manager,user):
    manager.require(user,Permission.ORDERS_VIEW)
    if not any(role in WORKSHOP_ROLES for role in split_roles(user.role)):return []
    result=[]
    for key in allowed_workshops(user):
        db=manager.database(key,user).backend
        with db.read_conn() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='order_notifications'").fetchone():continue
            rows=conn.execute("""SELECT * FROM order_notifications
                WHERE owner_id=? OR (owner_id IS NULL AND owner_username=?) ORDER BY id DESC LIMIT 100""",(user.id,user.username)).fetchall()
        result.extend({**dict(r),"workshop_key":key} for r in rows)
    # DB timestamps use dd-mm-yyyy, parse for ordering rather than lexicographic date order.
    from datetime import datetime
    return sorted(result,key=lambda r:(datetime.strptime(r["created_at"],"%d-%m-%Y %H:%M:%S"),r["id"]),reverse=True)


def unread_count(manager,user):
    manager.require(user,Permission.ORDERS_VIEW)
    if not any(role in WORKSHOP_ROLES for role in split_roles(user.role)):return 0
    count=0
    for key in allowed_workshops(user):
        db=manager.database(key,user).backend
        with db.read_conn() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='order_notifications'").fetchone():
                count+=conn.execute("SELECT COUNT(*) FROM order_notifications WHERE read_at IS NULL AND (owner_id=? OR (owner_id IS NULL AND owner_username=?))",(user.id,user.username)).fetchone()[0]
    return count


def mark_read(manager,user,key,ident=None):
    db=manager.database(key,user)
    params=[now_text(),user.id,user.username]
    query="UPDATE order_notifications SET read_at=? WHERE read_at IS NULL AND (owner_id=? OR (owner_id IS NULL AND owner_username=?))"
    if ident is not None:query+=" AND id=?";params.append(ident)
    with db.backend.write_conn() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='order_notifications'").fetchone():conn.execute(query,params)


class _NotificationSignals(QObject):
    loaded=pyqtSignal(object,int,str)


class NotificationPopup(QFrame):
    def __init__(self,owner):
        super().__init__(owner,Qt.Popup|Qt.FramelessWindowHint);self.owner=owner;self.setObjectName("NotificationPopup");self.setFixedSize(460,450)
        dark=owner.ui_settings.theme=="dark";bg="#1C2537" if dark else "#FFFFFF";fg="#F5F5F7" if dark else "#1D1D1F";card="#26314A" if dark else "#F7F9FC"
        self.setStyleSheet(f"QFrame#NotificationPopup{{background:{bg};color:{fg};border:1px solid #5A749B;border-radius:15px;}} QFrame#NotificationPopup QLabel{{color:{fg};}} QScrollArea,QScrollArea>QWidget>QWidget{{background:{bg};border:none;}} QFrame#NotificationCard{{background:{card};color:{fg};border:1px solid #5A749B;border-radius:9px;padding:3px;}}")
        root=QVBoxLayout(self);root.setContentsMargins(16,14,16,14);top=QHBoxLayout();h=QLabel("Уведомления");h.setStyleSheet("font-size:19px;font-weight:800;");top.addWidget(h);top.addStretch();allread=QPushButton("Прочитать все");allread.clicked.connect(self.read_all);top.addWidget(allread);root.addLayout(top)
        self.status=QLabel("Загрузка…");self.status.setWordWrap(True);root.addWidget(self.status)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);root.addWidget(scroll,1);self.content=QWidget();self.content.setObjectName("NotificationContent");self.rows=QVBoxLayout(self.content);self.rows.setContentsMargins(2,2,2,2);self.rows.addStretch();scroll.setWidget(self.content)
        self.render(owner._notification_items)
    def render(self,items,error=""):
        while self.rows.count():
            item=self.rows.takeAt(0)
            if item.widget():item.widget().deleteLater()
        if error:self.status.setText("Не удалось прочитать уведомления: "+error)
        else:self.status.setText(f"Непрочитанных: {self.owner._notification_count} · последние {len(items)} сообщений")
        if not items and not error:
            empty=QLabel("Изменений Ваших нарядов другими пользователями пока нет.");empty.setWordWrap(True);self.rows.addWidget(empty)
        from .workshops import WORKSHOPS
        for n in items:
            card=QFrame();card.setObjectName("NotificationCard");card.setStyleSheet("QFrame#NotificationCard{border:1px solid "+("#16B9B0" if not n["read_at"] else "#738097")+";border-radius:9px;padding:3px;}");l=QVBoxLayout(card)
            stamp=QLabel(("● " if not n["read_at"] else "")+WORKSHOPS[n["workshop_key"]]+" · "+n["created_at"]);stamp.setTextFormat(Qt.PlainText);stamp.setStyleSheet("font-size:10px;color:#16B9B0;border:0;");l.addWidget(stamp)
            text=QLabel(n["message"]);text.setTextFormat(Qt.PlainText);text.setWordWrap(True);text.setStyleSheet("border:0;");l.addWidget(text)
            button=QPushButton("Посмотреть версию "+n["version"]);button.clicked.connect(lambda _,notice=n:self.open_notice(notice));l.addWidget(button);self.rows.addWidget(card)
        self.rows.addStretch()
    def read_all(self):
        try:
            for key in allowed_workshops(self.owner.user):mark_read(self.owner.workshop_manager,self.owner.user,key)
            self.owner.refresh_notifications()
        except Exception as exc:self.status.setText(str(exc))
    def open_notice(self,n):
        try:
            if int(n.get("id",0)) < 0:
                self.hide();self.owner.show_news(n);return
            mark_read(self.owner.workshop_manager,self.owner.user,n["workshop_key"],n["id"])
            self.owner.refresh_notifications();self.hide();self.owner.open_notification_order(n)
        except Exception as exc:self.status.setText(str(exc))

"""Click-driven master training with real controls and an isolated practice order."""
import json
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                            QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .domain import OrderLine, dec
from .help_surface import opaque_help, center_dialog
from .i18n import REVERSE
from .security import ALL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS, Permission, SessionUser


def capabilities(user):
    result=set(user.permissions)
    if user.has_role("Администратор"):
        result.intersection_update(DEFAULT_ROLE_PERMISSIONS["Мастер Упаковка"])
    return result


def lesson_keys(user):
    allowed=capabilities(user);keys=[]
    if Permission.ORDERS_VIEW not in allowed:
        allowed.difference_update({Permission.ORDERS_CREATE,Permission.ORDERS_EDIT,Permission.ORDERS_HISTORY})
    if Permission.ORDERS_CREATE in allowed:
        keys += ["create","date","shift","master","department","employees","works","hours","boxes","weight","save"]
    if Permission.ORDERS_EDIT in allowed:keys += ["edit_hours","edit_save"]
    if Permission.ORDERS_HISTORY in allowed:keys.append("history")
    if Permission.ADMIN_VIEW in allowed:
        keys.append("administration")
        for code,key in ((Permission.DATA_SYNC,"admin_sync"),(Permission.AUDIT_VIEW,"admin_audit"),
                         (Permission.BACKUP_MANAGE,"admin_backup"),(Permission.DIAGNOSTICS_VIEW,"admin_diagnostics")):
            if code in allowed:keys.append(key)
    return keys


LESSONS={
 "create":("Откройте создание наряда","Нажмите сюда, чтобы открыть окно создания наряда. Дальше будем заполнять учебный пример."),
 "date":("Выберите дату","Нажмите значок календаря, выберите дату наряда и нажмите «Применить»."),
 "shift":("Выберите смену","Откройте список и выберите дневную или ночную смену."),
 "master":("Укажите мастера","Откройте список и выберите учебного мастера, ответственного за смену."),
 "department":("Выберите подразделение","Выберите учебное подразделение, к которому относится наряд."),
 "employees":("Добавьте работника","Нажмите «Добавить работников». В открывшемся списке отметьте учебного работника и подтвердите выбор."),
 "works":("Добавьте работу","Нажмите «Добавить работы», отметьте учебную работу и подтвердите выбор."),
 "hours":("Введите часы","Нажмите подсвеченную ячейку, введите часы работы, например 8, и завершите ввод клавишей Enter."),
 "boxes":("Укажите количество коробок","Введите количество коробок, например 12. После ввода нажмите Enter."),
 "weight":("Укажите вес коробки","Введите вес одной коробки, например 3 кг. Итоговый вес и оплата рассчитываются автоматически."),
 "save":("Сохраните учебный наряд","Нажмите «Сохранить». Так завершается создание наряда. Этот пример останется только в обучении."),
 "edit_hours":("Попробуйте редактирование","Сохранённый учебный наряд открыт для исправления. Справа в шапке мигает отметка режима. Измените часы в выделенной ячейке."),
 "edit_save":("Сохраните исправление","Нажмите «Сохранить»: появится новая версия, а первоначальные значения останутся в истории."),
 "history":("Посмотрите историю","Здесь отображаются авторы и время изменений. Нажмите на подсвеченный виджет — откроем подробную историю вашего учебного наряда."),
 "administration":("Откройте администрирование","Нажмите вкладку «Администрирование». Покажем только те функции, которые доступны мастеру с вашими правами."),
 "admin_sync":("Синхронизация","Эта кнопка обновляет данные из общей базы. Если изменения коллеги ещё не появились, начните с неё. Нажмите «Далее», чтобы продолжить обучение."),
 "admin_audit":("Журнал действий","Здесь можно проверить пользователя, время и действие. Период и фильтр пользователя помогают найти нужную запись."),
 "admin_backup":("Резервные копии","Эта кнопка создаёт резервную копию рабочих данных. В обучении копия не создаётся. Восстановление доступно только при отдельном разрешении."),
 "admin_diagnostics":("Диагностика","В этом разделе проверяют доступность базы и состояние приложения. При неполадках результаты помогут администратору разобраться."),
}


class CoachOverlay(QFrame):
    def __init__(self, tour, host, title, text, number, total, informational=False):
        super().__init__(host)
        self.tour,self.host,self.target=tour,host,QRect()
        self.number=number;self.phase=0.0
        self.extra_holes=[]
        self.setProperty("plainSurface",True)
        self.setObjectName("ClickTrainingOverlay")
        self.setAttribute(Qt.WA_TranslucentBackground,True)
        self.setAttribute(Qt.WA_NoSystemBackground,True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("QFrame#ClickTrainingOverlay{background:transparent;border:0;}")
        self.setGeometry(host.rect())
        self.card=QFrame(self);self.card.setObjectName("TrainingCard")
        opaque_help(self.card,tour.owner.ui_settings.theme)
        layout=QVBoxLayout(self.card);layout.setContentsMargins(18,15,18,15);layout.setSpacing(10)
        tag=QLabel(f"ШАГ {number} ИЗ {total} · ОБУЧЕНИЕ МАСТЕРА",self.card);tag.setObjectName("TrainingKicker");layout.addWidget(tag)
        heading=QLabel(title,self.card);heading.setObjectName("TrainingTitle");heading.setWordWrap(True);layout.addWidget(heading)
        body=QLabel(text,self.card);body.setWordWrap(True);layout.addWidget(body)
        row=QHBoxLayout();stop=QPushButton("Завершить обучение",self.card);stop.clicked.connect(tour.finish);row.addWidget(stop);row.addStretch()
        if informational:
            next_button=QPushButton("Далее",self.card);next_button.setObjectName("PrimaryButton");next_button.clicked.connect(tour.next);row.addWidget(next_button)
        layout.addLayout(row)
        self.card.setFixedWidth(min(400,max(280,host.width()-32)))
        self.card.adjustSize()
        self.card.hide()
        host.installEventFilter(self)
        self.animation=QVariantAnimation(self);self.animation.setDuration(1400);self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.setLoopCount(-1)
        self.animation.valueChanged.connect(self._pulse)
        self.show();self.raise_();self.animation.start()

    def _pulse(self,value):self.phase=float(value);self.update()

    def highlight(self, rect):
        self.target=rect.intersected(self.rect())
        vertical_space=max(self.target.top()-24,self.height()-self.target.bottom()-24)
        if vertical_space<self.card.height():
            space=max(self.target.left()-24,self.width()-self.target.right()-24)
            self.card.setFixedWidth(min(400,max(260,space)))
            self.card.adjustSize()
        width,height=self.card.width(),self.card.height()
        candidates=[QPoint(self.target.left(),self.target.bottom()+18),QPoint(self.target.right()+18,self.target.top()),
                    QPoint(self.target.left(),self.target.top()-height-18),QPoint(self.target.left()-width-18,self.target.top())]
        def fit(point):return QPoint(max(12,min(point.x(),self.width()-width-12)),max(12,min(point.y(),self.height()-height-12)))
        best=min((fit(point) for point in candidates),key=lambda point: self.target.intersected(QRect(point,self.card.size())).width()*self.target.intersected(QRect(point,self.card.size())).height())
        self.card.move(best)
        self.card.show()
        mask=QRegion(self.rect()).subtracted(QRegion(self.target.adjusted(1,1,-1,-1)))
        for hole in self.extra_holes:mask=mask.subtracted(QRegion(hole))
        self.setMask(mask.united(QRegion(self.card.geometry())))
        self.update()

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Resize:
            self.setGeometry(self.host.rect());self.tour.position_target()
        return False

    def hideEvent(self,event):
        self.animation.stop();super().hideEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        shade=QPainterPath();shade.setFillRule(Qt.OddEvenFill);shade.addRect(QRectF(self.rect()))
        if not self.target.isEmpty():shade.addRoundedRect(QRectF(self.target.adjusted(-3,-3,3,3)),10,10)
        painter.fillPath(shade,QColor(6,20,37,130))
        if self.target.isEmpty():return
        painter.setPen(QPen(QColor("#62bcff"),2));painter.drawRoundedRect(QRectF(self.target.adjusted(-4,-4,4,4)),10,10)
        center=QPoint(max(24,min(self.target.left()+10,self.width()-25)),max(26,self.target.top()-13))
        painter.setBrush(Qt.NoBrush)
        for offset in (0.0,.5):
            phase=(self.phase+offset)%1
            painter.setPen(QPen(QColor(74,177,255,int(150*(1-phase))),2))
            radius=17+phase*18;painter.drawEllipse(QRectF(center.x()-radius,center.y()-radius,2*radius,2*radius))
        painter.setPen(QPen(QColor("#b5e3ff"),1.5));painter.setBrush(QColor("#087bfa"));painter.drawEllipse(center,16,16)
        font=painter.font();font.setPixelSize(15);font.setBold(True);painter.setFont(font);painter.setPen(Qt.white)
        painter.drawText(QRect(center.x()-16,center.y()-16,32,32),Qt.AlignCenter,str(self.number))


class GuidedTour(QObject):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner;self.keys=lesson_keys(owner.user);self.index=-1;self.running=True
        self.original_tab=owner.tabs.currentIndex();self.editor=None;self.picker=None;self.coach=None
        self.target=QRect();self.host=owner;self.temp=None;self.demo_order=None;self.editing=False
        self._eat_release=False;self._pending=False;self._changing=False
        QApplication.instance().installEventFilter(self)

    @property
    def key(self):return self.keys[self.index] if 0<=self.index<len(self.keys) else ""

    def begin(self):self.next()

    def next(self):
        if not self.running or self._pending:return
        self.index+=1
        if self.index>=len(self.keys):self.finish(completed=True);return
        self.present()

    def queue_next(self):
        if self._pending or not self.running:return
        self._pending=True
        def run():
            self._pending=False
            if self.running:self.next()
        QTimer.singleShot(0,run)

    def clear_coach(self):
        if self.coach is not None:
            self.coach.hide();self.coach.deleteLater();self.coach=None

    def _ensure_data(self,seed=False):
        if self.temp is None:
            from .db import Database
            self.temp=tempfile.TemporaryDirectory(prefix="smartorder-practice-")
            self.db=Database(Path(self.temp.name)/"practice.db")
            self.actor=SessionUser(-1,"Учебный мастер","Администратор",frozenset(ALL_PERMISSIONS))
            self.worker=self.db.add_employee(self.actor,"Иванов Иван · учебный работник")
            self.master=self.db.add_employee(self.actor,"Учебный мастер",True)
            self.department=self.db.add_department(self.actor,"Учебное подразделение")
            self.work=self.db.add_work_type(self.actor,"Упаковка готовой продукции · учебная работа","0000001","2")
        if seed and self.demo_order is None:
            line=OrderLine(self.worker,"Иванов Иван · учебный работник",self.work,"Упаковка готовой продукции · учебная работа","0000001",Decimal(2),Decimal(8),Decimal(12),Decimal(3))
            identity=self.db.save_order(self.actor,date.today().strftime("%d-%m-%Y"),"Дневная",self.master,self.department,[line])
            self.demo_order=self.db.get_order(identity)

    def make_editor(self,editing):
        if self.editor is not None and self.editing==editing:return self.editor
        self._ensure_data(seed=editing)
        self._changing=True
        if self.editor is not None:self.editor.reject();self.editor.deleteLater()
        from .heavy_ui import HeavyWorkOrderDialog
        tour=self
        class PracticeEditor(HeavyWorkOrderDialog):
            def _save_draft(self):pass
            def _accept(self):tour.save(self)
        dialog=PracticeEditor(self.db,self.owner.user,self.demo_order if editing else None,parent=self.owner)
        dialog.setWindowTitle("Учебный пример · "+("Редактирование наряда" if editing else "Создание наряда"))
        dialog.setWindowModality(Qt.WindowModal)
        if not editing:
            for combo in (dialog.shift,dialog.master,dialog.department):combo.setCurrentIndex(-1)
        self.editor=dialog;self.editing=editing
        dialog.order_date._popup.dateSelected.connect(lambda value:self.field_done("date"))
        for name in ("shift","master","department"):
            getattr(dialog,name).currentIndexChanged.connect(lambda index,key=name:self.field_done(key) if index>=0 else None)
        dialog.table.itemChanged.connect(self.manual_changed)
        dialog.finished.connect(lambda result:self.editor_finished(dialog,result))
        self._changing=False;dialog.show()
        return dialog

    def field_done(self,key):
        if self.running and self.key==key:self.queue_next()

    def manual_changed(self,item):
        wanted={"hours":1,"boxes":5,"weight":6,"edit_hours":1}.get(self.key)
        if wanted is None or item.column()!=wanted:return
        value=dec(item.text())
        if value is None or not value.is_finite() or value<=0 or wanted==1 and value>24:return
        if self.key=="edit_hours" and self.demo_order and value==self.demo_order["lines"][0].hours:return
        self.queue_next()

    def save(self,dialog):
        if not self.running or self.key not in ("save","edit_save"):return
        error=dialog._validate()
        if error:QMessageBox.warning(dialog,"Проверка учебного наряда",error);return
        data=dialog.get_data()
        identity=self.db.save_order(self.owner.user,**data,parent_id=dialog.order_id if self.editing else None)
        self.demo_order=self.db.get_order(identity)
        dialog._course_saved=True
        QDialog.accept(dialog)

    def editor_finished(self,dialog,result):
        if not self.running or self._changing:return
        if result==QDialog.Accepted and getattr(dialog,"_course_saved",False):self.queue_next()
        else:self.finish()

    def present(self):
        if not self.running:return
        self.clear_coach()
        self.target=QRect()
        key=self.key
        if key not in lesson_keys(self.owner.user) or not getattr(self.owner,"_account_active",True):self.finish();return
        editor_keys={"date","shift","master","department","employees","works","hours","boxes","weight","save","edit_hours","edit_save"}
        if key in editor_keys:
            self.host=self.make_editor(key.startswith("edit_"))
        else:
            if self.editor is not None:self.editor.hide()
            self.host=self.owner
            if key.startswith("admin_"):self.owner.tabs.setCurrentIndex(3)
            elif self.owner.tabs.isTabEnabled(0):self.owner.tabs.setCurrentIndex(0)
        title,text=LESSONS[key]
        self.host.raise_();self.host.activateWindow()
        self.coach=CoachOverlay(self,self.host,title,text,self.index+1,len(self.keys),key.startswith("admin_"))
        self.position_target()

    def work_row(self):
        for row in range(self.editor.table.rowCount()):
            item=self.editor.table.item(row,2)
            if item is not None and item.text() and not self.editor._is_total(row):return row
        return 0

    def native_target(self):
        key=self.key;host=self.host
        if self.picker is not None and self.picker.isVisible():
            listing=self.picker.list
            first=listing.visualItemRect(listing.item(0)) if listing.count() else listing.viewport().rect()
            first.setWidth(min(260,first.width()))
            box=self.picker.findChild(QDialogButtonBox)
            if box is not None and self.coach is not None:
                button=box.button(QDialogButtonBox.Ok)
                self.coach.extra_holes=[QRect(button.mapTo(host,QPoint()),button.size())]
            return QRect(listing.viewport().mapTo(host,first.topLeft()),first.size())
        if key in ("hours","boxes","weight","edit_hours"):
            table=self.editor.table;column={"hours":1,"boxes":5,"weight":6,"edit_hours":1}[key]
            row=self.work_row();table.setCurrentCell(row,column);table.scrollToItem(table.item(row,column))
            rect=table.visualItemRect(table.item(row,column))
            return QRect(table.viewport().mapTo(host,rect.topLeft()),rect.size())
        if key=="administration":
            bar=self.owner.tabs.tabBar();rect=bar.tabRect(3);return QRect(bar.mapTo(host,rect.topLeft()),rect.size())
        names={"create":"create_order_btn","history":"info_panel","employees":"add_employee_btn","works":"add_work_btn",
               "save":"button_box","edit_save":"button_box","admin_sync":"admin_sync_btn","admin_audit":"audit_table"}
        widget=getattr(self.editor if host is self.editor else self.owner,names.get(key,key),None)
        if key in ("save","edit_save") and widget is not None:widget=widget.button(QDialogButtonBox.Ok)
        if widget is None and key.startswith("admin_"):
            phrases={"admin_backup":("Создать бэкап","Создать бэкап"),"admin_diagnostics":("Центр диагностики",)}
            widget=next((button for button in self.owner.tabs.widget(3).findChildren(QPushButton)
                         if REVERSE.get(button.text(),button.text()) in phrases.get(key,())),None)
        if widget is None:widget=self.owner.tabs.widget(3) if key.startswith("admin_") else host
        parent=widget.parentWidget()
        while parent is not None:
            if isinstance(parent,QScrollArea):parent.ensureWidgetVisible(widget);break
            parent=parent.parentWidget()
        return QRect(widget.mapTo(host,QPoint()),widget.size())

    def position_target(self):
        if not self.running or self.coach is None:return
        coach=self.coach;key=self.key
        if self.host is self.owner and key in ("create","history") and getattr(self.owner,"_glass_painted",False):
            target="create" if key=="create" else "history-panel"
            script='(function(){var e=document.getElementById('+json.dumps(target)+');e.scrollIntoView({block:"nearest",inline:"nearest"});var r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height];})()'
            def got(bounds):
                if not self.running or self.coach is not coach or not bounds:return
                origin=self.owner._glass.mapTo(self.owner,QPoint())
                self.set_target(QRect(origin.x()+int(bounds[0]),origin.y()+int(bounds[1]),int(bounds[2]),int(bounds[3])))
            self.owner._glass.page().runJavaScript(script,got)
        else:self.set_target(self.native_target())

    def set_target(self,rect):
        if self.coach is None:return
        rect=rect.intersected(self.host.rect())
        self.target=QRect(self.host.mapToGlobal(rect.topLeft()),rect.size())
        self.coach.highlight(rect)

    def open_picker(self,dialog):
        if not self.running or sip.isdeleted(dialog):return
        self.clear_coach();self.picker=dialog;self.host=dialog
        title="Выберите работника" if self.key=="employees" else "Выберите работу"
        text="Отметьте учебную строку в списке и нажмите ОК. После подтверждения продолжим заполнение наряда."
        self.coach=CoachOverlay(self,dialog,title,text,self.index+1,len(self.keys))
        dialog.accepted.connect(self.picker_accepted)
        dialog.rejected.connect(self.picker_rejected)
        self.position_target()

    def picker_accepted(self):
        if not self.running:return
        self.picker=None;self.queue_next()

    def picker_rejected(self):
        if not self.running:return
        self.picker=None;QTimer.singleShot(0,self.present)

    def click_target(self):
        if self.key=="create":self.next()
        elif self.key=="history":
            self._ensure_data(seed=True)
            from .order_history import history_html
            self.clear_coach()
            self.owner._apply_history_details((self.owner.workshop,history_html(self.db,self.demo_order["info"]["id"])))
            dialog=self.owner._history_details_dialog
            dialog.finished.connect(lambda result:self.queue_next())
        elif self.key=="administration":self.owner.tabs.setCurrentIndex(3);self.next()
        elif self.key.startswith("admin_"):self.next()

    def eventFilter(self,watched,event):
        if not self.running:return False
        kind=event.type()
        if watched is self.owner and kind==QEvent.Close:self.finish();return False
        if kind==QEvent.Show and isinstance(watched,QDialog) and self.editor is not None:
            from .heavy_ui import EmployeeSelectionDialog,WorkSelectionDialog
            expected=EmployeeSelectionDialog if self.key=="employees" else WorkSelectionDialog if self.key=="works" else None
            if expected and isinstance(watched,expected):QTimer.singleShot(0,lambda dialog=watched:self.open_picker(dialog))
        if isinstance(watched,QFrame) and watched.objectName()=="OrderCalendarPopup" and self.key=="date":
            if kind==QEvent.Show:
                def calendar_target(popup=watched):
                    if self.running and self.key=="date" and popup.isVisible():self.set_target(popup.geometry());self.coach.raise_()
                QTimer.singleShot(0,calendar_target)
            elif kind==QEvent.Hide:QTimer.singleShot(0,self.position_target)
        if kind==QEvent.MouseButtonRelease and self._eat_release:
            self._eat_release=False;return True
        if kind==QEvent.MouseButtonPress and hasattr(event,"globalPos") and event.button()==Qt.LeftButton:
            if self.coach is None or not isinstance(watched,QWidget) or watched.window() is not self.host.window():return False
            if self.coach is not None and QRect(self.coach.card.mapToGlobal(QPoint()),self.coach.card.size()).contains(event.globalPos()):return False
            if self.key in ("create","history","administration") or self.key.startswith("admin_"):
                if self.target.contains(event.globalPos()):
                    self._eat_release=True;QTimer.singleShot(0,self.click_target);return True
        if kind==QEvent.KeyPress and event.key()==Qt.Key_Escape:
            if QApplication.activePopupWidget() is not None:return False
            if self.editor is not None and self.editor.order_date._popup.isVisible():return False
            self.finish();return True
        if kind==QEvent.KeyPress and isinstance(watched,QWidget) and watched.window() is self.owner:
            on_card=self.coach is not None and (watched is self.coach.card or self.coach.card.isAncestorOf(watched))
            if not on_card and event.key()!=Qt.Key_F1:
                if event.key() in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Space) and (self.key in ("create","history","administration") or self.key.startswith("admin_")):
                    self.click_target()
                return True
        return False

    def finish(self,checked=False,completed=False):
        if not self.running:return
        self.running=False;self.clear_coach()
        QApplication.instance().removeEventFilter(self)
        if self.picker is not None and not sip.isdeleted(self.picker):self.picker.reject()
        if self.editor is not None and not sip.isdeleted(self.editor):self.editor.reject();self.editor.deleteLater()
        if self.temp is not None:self.temp.cleanup()
        if not sip.isdeleted(self.owner):
            if self.owner.tabs.isTabEnabled(self.original_tab):self.owner.tabs.setCurrentIndex(self.original_tab)
            self.owner._master_tour=None
            if completed:
                dialog=QDialog(self.owner);opaque_help(dialog,self.owner.ui_settings.theme);dialog.setWindowTitle("Обучение завершено")
                layout=QVBoxLayout(dialog);label=QLabel("Готово! Теперь вы знаете, как создать и исправить наряд, посмотреть историю и найти доступные функции администрирования.",dialog);label.setWordWrap(True);layout.addWidget(label)
                button=QPushButton("Начать работу",dialog);button.setObjectName("PrimaryButton");button.clicked.connect(dialog.accept);layout.addWidget(button)
                dialog.setFixedWidth(460);dialog.setAttribute(Qt.WA_DeleteOnClose);self.owner._training_complete=dialog;center_dialog(dialog,self.owner);dialog.show()
        self.deleteLater()

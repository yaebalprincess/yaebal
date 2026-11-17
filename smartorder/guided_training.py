"""Click-driven master training with real controls and an isolated practice order."""
import json
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFrame,
                            QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .domain import OrderLine, dec
from .help_surface import center_dialog
from .i18n import REVERSE
from .security import ALL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS, Permission, SessionUser
from .training_overlay import CoachOverlay, TutorialDialog


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
    if Permission.ORDERS_EDIT in allowed:keys += ["edit","edit_any","edit_save"]
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
 "hours":("Введите часы","Нажмите подсвеченную ячейку и введите часы работы, например 8. Затем нажмите «ОК» в этой подсказке."),
 "boxes":("Укажите количество коробок","Введите количество коробок, например 12. Затем нажмите «ОК» в этой подсказке."),
 "weight":("Укажите вес коробки","Введите вес одной коробки, например 3 кг, и нажмите «ОК». Итоговый вес и оплата рассчитываются автоматически."),
 "save":("Сохраните учебный наряд","Нажмите «Сохранить». Так завершается создание наряда. Этот пример останется только в обучении."),
 "edit":("Попробуйте редактирование","Здесь показан только ваш учебный наряд. Он уже выбран в списке. Нажмите подсвеченную кнопку «Редактировать». Рабочие наряды вернутся после обучения."),
 "edit_any":("Измените любые данные","Исправьте часы, количество коробок, вес, дату или комментарий учебного наряда. Справа в шапке мигает отметка режима редактирования. После изменения нажмите «ОК» в этой подсказке."),
 "edit_save":("Сохраните исправление","Нажмите «Сохранить»: появится новая версия, а первоначальные значения останутся в истории."),
 "history":("Посмотрите историю","Здесь отображаются авторы и время изменений. Нажмите на подсвеченный виджет — откроем подробную историю вашего учебного наряда."),
 "administration":("Откройте администрирование","Нажмите вкладку «Администрирование». Покажем только те функции, которые доступны мастеру с вашими правами."),
 "admin_sync":("Синхронизация","Эта кнопка обновляет данные из общей базы. Если изменения коллеги ещё не появились, начните с неё. Нажмите «Далее», чтобы продолжить обучение."),
 "admin_audit":("Журнал действий","Здесь можно проверить пользователя, время и действие. Период и фильтр пользователя помогают найти нужную запись."),
 "admin_backup":("Резервные копии","Эта кнопка создаёт резервную копию рабочих данных. В обучении копия не создаётся. Восстановление доступно только при отдельном разрешении."),
 "admin_diagnostics":("Диагностика","В этом разделе проверяют доступность базы и состояние приложения. При неполадках результаты помогут администратору разобраться."),
}


class GuidedTour(QObject):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner;self.keys=lesson_keys(owner.user);self.index=-1;self.running=True
        self.original_tab=owner.tabs.currentIndex();self.editor=None;self.picker=None;self.coach=None
        self.target=QRect();self.host=owner;self.temp=None;self.demo_order=None;self.editing=False
        self._eat_release=False;self._pending=False;self._changing=False;self._confirming=False
        self.layers={};self._edit_baseline=None;self.practice_history=[]
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
            self.coach.passive();self.coach=None

    def new_coach(self, host, title, text, informational=False, confirm=False):
        old=self.layers.pop(host,None)
        if old is not None and not sip.isdeleted(old):old.hide();old.deleteLater()
        self.coach=CoachOverlay(self,host,title,text,self.index+1,len(self.keys),informational,confirm)
        self.layers[host]=self.coach

    def main_state(self, state):
        """The practice list is presentation-only; production models stay intact."""
        state.update(rows=[],selected=None,history=[],draftView=False,
                     emptyMessage="Учебная среда: создайте первый наряд.",busy=False,topRestricted=False)
        for name,action in state["actions"].items():
            action["enabled"] = name=="create" and self.key=="create" or name=="edit" and self.key=="edit"
        if self.demo_order is not None:
            info=self.demo_order["info"]
            state["rows"]=[{"key":"practice", "draft":False, "cells":[str(info.get("version","1")),
                info["order_date"].replace("-","."),info["shift_type"],info.get("master", "Учебный мастер"),
                info.get("department", "Учебное подразделение"),info.get("registration_date", "")]}]
            state["selected"]="practice"
            for index,record in enumerate(self.practice_history):
                state["history"].append(("Создал" if index==0 else "Редактировал")+": "+str(record["edited_by"])+" · "+str(record["edit_date"] or record["registration_date"]))
        return state

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
            self.practice_history=list(reversed(self.db.order_history(identity)))

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
            def reject(self):
                if tour.running and not tour._changing:tour.request_finish()
                else:QDialog.reject(self)
            def closeEvent(self,event):
                if tour.running and not tour._changing:event.ignore();tour.request_finish()
                else:QDialog.closeEvent(self,event)
        dialog=PracticeEditor(self.db,self.owner.user,self.demo_order if editing else None,parent=self.owner)
        dialog.setWindowTitle("Учебный пример · "+("Редактирование наряда" if editing else "Создание наряда"))
        dialog.setWindowModality(Qt.WindowModal)
        if not editing:
            for combo in (dialog.shift,dialog.master,dialog.department):combo.setCurrentIndex(-1)
        self.editor=dialog;self.editing=editing
        self._edit_baseline=dialog.get_data() if editing else None
        dialog.order_date._popup.dateSelected.connect(lambda value:self.field_done("date"))
        for name in ("shift","master","department"):
            getattr(dialog,name).currentIndexChanged.connect(lambda index,key=name:self.field_done(key) if index>=0 else None)
        dialog.table.itemChanged.connect(self.manual_changed)
        for field in (dialog.order_date,):field.dateChanged.connect(self.changed_any)
        for combo in (dialog.shift,dialog.master,dialog.department):combo.currentIndexChanged.connect(self.changed_any)
        dialog.comment.textChanged.connect(self.changed_any)
        dialog.separate_worker_check.toggled.connect(self.changed_any)
        dialog.finished.connect(lambda result:self.editor_finished(dialog,result))
        self._changing=False;dialog.show()
        return dialog

    def field_done(self,key):
        if self.running and self.key==key:self.queue_next()

    def manual_changed(self,item):
        if self.key=="edit_any":self.changed_any();return
        wanted={"hours":1,"boxes":5,"weight":6}.get(self.key)
        if wanted is None or item.column()!=wanted:return
        value=dec(item.text())
        if value is None or not value.is_finite() or value<=0 or wanted==1 and value>24:return
        self.update_confirm()

    def changed_any(self,*_):
        if self.running and self.key=="edit_any" and not self._changing:self.update_confirm()

    def value_ready(self):
        if self.editor is None:return False
        if self.key=="edit_any":return self.editor.get_data()!=self._edit_baseline
        column={"hours":1,"boxes":5,"weight":6}.get(self.key)
        if column is None:return False
        item=self.editor.table.item(self.work_row(),column)
        value=dec(item.text()) if item is not None else None
        return value is not None and value.is_finite() and value>0 and (column!=1 or value<=24)

    def update_confirm(self):
        if self.coach is not None and self.coach.card.confirm is not None:
            # Keep OK clickable while an editor holds uncommitted text; the
            # focus transfer commits the cell before confirm_value validates it.
            self.coach.card.confirm.setEnabled(True)

    def confirm_value(self):
        if not self.running:return
        if self.coach is not None:self.coach.card.setFocus(Qt.OtherFocusReason)
        def committed():
            if not self.running:return
            if self.value_ready():self.queue_next()
            else:
                self.coach.card.body.setText("Измените данные учебного наряда." if self.key=="edit_any" else "Введите положительное число в подсвеченную ячейку, затем нажмите «ОК».")
                self.position_target()
        QTimer.singleShot(0,committed)

    def save(self,dialog):
        if not self.running or self.key not in ("save","edit_save"):return
        error=dialog._validate()
        if error:QMessageBox.warning(dialog,"Проверка учебного наряда",error);return
        data=dialog.get_data()
        identity=self.db.save_order(self.owner.user,**data,parent_id=dialog.order_id if self.editing else None)
        self.demo_order=self.db.get_order(identity)
        self.practice_history=list(reversed(self.db.order_history(identity)))
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
        if key in {"edit","history"}:self._ensure_data(seed=True)
        if key not in lesson_keys(self.owner.user) or not getattr(self.owner,"_account_active",True):self.finish();return
        editor_keys={"date","shift","master","department","employees","works","hours","boxes","weight","save","edit_any","edit_save"}
        if key in editor_keys:
            self.host=self.make_editor(key.startswith("edit_"))
        else:
            if self.editor is not None:self.editor.hide()
            self.host=self.owner
            if key.startswith("admin_"):self.owner.tabs.setCurrentIndex(3)
            elif self.owner.tabs.isTabEnabled(0):self.owner.tabs.setCurrentIndex(0)
        title,text=LESSONS[key]
        self.host.raise_();self.host.activateWindow()
        self.new_coach(self.host,title,text,key.startswith("admin_"),key in {"hours","boxes","weight","edit_any"})
        if hasattr(self.owner,"_publish_glass_state"):self.owner._publish_glass_state(force=True)
        QTimer.singleShot(0,self.position_target)

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
        if key in ("hours","boxes","weight"):
            table=self.editor.table;column={"hours":1,"boxes":5,"weight":6}[key]
            row=self.work_row();table.setCurrentCell(row,column);table.scrollToItem(table.item(row,column))
            rect=table.visualItemRect(table.item(row,column))
            return QRect(table.viewport().mapTo(host,rect.topLeft()),rect.size())
        if key=="edit_any":
            self.coach.extra_holes=[QRect(widget.mapTo(host,QPoint()),widget.size()) for widget in
                (self.editor.order_date,self.editor.shift,self.editor.master,self.editor.department,self.editor.comment,
                 self.editor.separate_worker_check,self.editor.add_employee_btn,self.editor.add_work_btn,self.editor.delete_row_btn)]
            return QRect(self.editor.table.mapTo(host,QPoint()),self.editor.table.size())
        if key=="administration":
            bar=self.owner.tabs.tabBar();rect=bar.tabRect(3);return QRect(bar.mapTo(host,rect.topLeft()),rect.size())
        names={"create":"create_order_btn","edit":"edit_order_btn","date":"order_date","history":"info_panel","employees":"add_employee_btn","works":"add_work_btn",
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
        if self.host is self.owner and key in ("create","edit","history") and getattr(self.owner,"_glass_painted",False):
            target={"create":"create","edit":"edit","history":"history-panel"}[key]
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
        self.new_coach(dialog,title,text)
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
        if self.key in ("create","edit"):self.next()
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
        if not self.running or self._confirming:return False
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
            if self.key in ("create","edit","history","administration") or self.key.startswith("admin_"):
                if self.target.contains(event.globalPos()):
                    self._eat_release=True;QTimer.singleShot(0,self.click_target);return True
        if kind==QEvent.KeyPress and event.key()==Qt.Key_Escape:
            if QApplication.activePopupWidget() is not None:return False
            if self.editor is not None and self.editor.order_date._popup.isVisible():return False
            self.request_finish();return True
        if kind==QEvent.KeyPress and isinstance(watched,QWidget) and watched.window() is self.owner:
            on_card=self.coach is not None and (watched is self.coach.card or self.coach.card.isAncestorOf(watched))
            if not on_card and event.key()!=Qt.Key_F1:
                if event.key() in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Space) and (self.key in ("create","edit","history","administration") or self.key.startswith("admin_")):
                    self.click_target()
                return True
        return False

    def request_finish(self,checked=False):
        if not self.running or self._confirming:return
        from .heavy_ui import question
        self._confirming=True
        try:answer=question(self.host,"Завершение обучения","Вы точно хотите закончить обучение?")
        finally:self._confirming=False
        if answer==QMessageBox.Yes:self.finish()

    def finish(self,checked=False,completed=False):
        if not self.running:return
        self.running=False;self.clear_coach()
        QApplication.instance().removeEventFilter(self)
        for layer in self.layers.values():
            if not sip.isdeleted(layer):layer.hide();layer.deleteLater()
        self.layers.clear()
        if getattr(self.owner,"_glass",None) is not None:
            self.owner._glass.page().runJavaScript("window.SmartOrderCoach&&window.SmartOrderCoach.hide()")
        if self.picker is not None and not sip.isdeleted(self.picker):self.picker.reject()
        if self.editor is not None and not sip.isdeleted(self.editor):self.editor.reject();self.editor.deleteLater()
        if self.temp is not None:self.temp.cleanup()
        if not sip.isdeleted(self.owner):
            if self.owner.tabs.isTabEnabled(self.original_tab):self.owner.tabs.setCurrentIndex(self.original_tab)
            self.owner._master_tour=None
            if hasattr(self.owner,"_publish_glass_state"):self.owner._publish_glass_state(force=True)
            if completed:
                dialog=TutorialDialog(self.owner);dialog.setWindowTitle("Обучение завершено")
                layout=QVBoxLayout(dialog);label=QLabel("Готово! Теперь вы знаете, как создать и исправить наряд, посмотреть историю и найти доступные функции администрирования.",dialog);label.setWordWrap(True);layout.addWidget(label)
                button=QPushButton("Начать работу",dialog);button.setObjectName("PrimaryButton");button.clicked.connect(dialog.accept);layout.addWidget(button)
                dialog.setFixedWidth(560);dialog.setAttribute(Qt.WA_DeleteOnClose);self.owner._training_complete=dialog;center_dialog(dialog,self.owner);dialog.show()
        self.deleteLater()

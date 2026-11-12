"""Section help and a permission-aware tour using disposable demonstration data."""
import hashlib
import json
import tempfile
from datetime import date
from decimal import Decimal
from html import escape
from pathlib import Path

from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                            QLabel, QPushButton, QShortcut, QTextBrowser, QVBoxLayout)
from PyQt5 import sip

from .config import local_state_dir
from .security import Permission, WORKSHOP_ROLES, split_roles


def help_allowed(user):
    return any(role == "Администратор" or role == "Мастер" or role in WORKSHOP_ROLES
               for role in split_roles(user.role))


SECTIONS = {
    "orders": ("Наряды", "create", "Выберите дату и цех. Сохранённые наряды и черновики отображаются в таблице.",
               ((Permission.ORDERS_CREATE, "Создать наряд: укажите смену, мастера и подразделение, добавьте работников и работы."),
                (Permission.ORDERS_EDIT, "Редактировать: выберите наряд и откройте редактор. Сохранение создаёт следующую версию."),
                (Permission.ORDERS_HISTORY, "История справа: нажмите на автора изменения, чтобы увидеть работы, поля и время этой версии."),
                (Permission.ORDERS_EXPORT, "Выгрузка и печать: две половины одной кнопки. Для печати откроется системный диалог с принтером по умолчанию."))),
    "editor": ("Редактор наряда", "versions", "Сведения о смене — сверху, состав работ — в таблице, действия — внизу.",
               ((Permission.ORDERS_CREATE, "Добавьте работников, затем назначьте работы. Двойной щелчок по ячейке работы открывает подбор; режим «Отдельный работник» использует свою кнопку."),
                (Permission.ORDERS_EDIT, "В режиме редактирования справа в шапке мигает отметка. Изменяйте часы и объёмы, затем сохраните новую версию."),
                (Permission.ORDERS_VIEW, "Название работы переносится по строкам. Ширина часов и кода закреплена, ручные пропорции остальных столбцов сохраняются для всех нарядов."))),
    "catalog": ("Номенклатура", "", "Справочник работ: наименование, код и расценка. Даты в таблице разделены с именами авторов.", ()),
    "people": ("Сотрудники, мастера и подразделения", "", "Переключайте вид справочника сверху. Поиск фильтрует строки; дата и автор создания или изменения показаны в одной ячейке.",
               ((Permission.EMPLOYEES_CREATE, "Добавьте сотрудника через поле ФИО и кнопку «Добавить». Мастера и подразделения создаются в соответствующем режиме."),
                (Permission.EMPLOYEES_IMPORT, "«Загрузить из Excel» позволяет заполнить справочник из файла."))),
    "admin": ("Администрирование", "", "Здесь находятся доступные вашей учётной записи операции синхронизации, резервных копий и журнала. Ориентируйтесь на активные кнопки и свои права.", ()),
    "analytics": ("Аналитика", "analytics", "Укажите период и фильтры. Методика объясняет расчёты. Масштаб интерфейса в этой вкладке не меняется.", ()),
    "personalization": ("Персонализация", "", "Выберите тему, язык, шрифт и масштаб. Сохраните настройки для запуска; синхронизация профиля переносит их между компьютерами через общую базу.", ()),
    "about": ("О приложении", "", "Информация о версии, текущей сессии и полное руководство программы.", ()),
}


def current_section(owner):
    active = QApplication.activeWindow()
    if active is not None and hasattr(active, "editor_columns"):
        return "editor"
    return ("orders", "catalog", "people", "admin", "analytics", "personalization", "about")[owner.tabs.currentIndex()]


def show_context_help(owner):
    if not help_allowed(owner.user) or not getattr(owner, "_account_active", True):
        return
    title, image, intro, features = SECTIONS[current_section(owner)]
    from .guide_site import screenshot
    dialog = QDialog(QApplication.activeWindow() or owner)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setObjectName("SectionHelp")
    dialog.setWindowTitle("Справка · " + title)
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.resize(820, 620)
    layout = QVBoxLayout(dialog)
    browser = QTextBrowser(dialog)
    browser.setOpenExternalLinks(False)
    paragraphs = "".join(f"<p>{escape(text)}</p>" for code, text in features if owner.can(code))
    picture = screenshot(image).replace('<img ', '<img width="700" ')
    browser.setHtml(f'<h1>{escape(title)}</h1><p>{escape(intro)}</p>{paragraphs}{picture}'
                    '<p>F1 открывает справку по текущему разделу.</p>')
    layout.addWidget(browser, 1)
    actions = QHBoxLayout()
    full = QPushButton("Полное руководство", dialog)
    full.clicked.connect(owner._open_guide)
    actions.addWidget(full)
    training = QPushButton("Пройти обучение", dialog)
    training.clicked.connect(lambda: (dialog.accept(), start_training(owner)))
    actions.addWidget(training)
    actions.addStretch()
    close = QPushButton("Закрыть", dialog)
    close.clicked.connect(dialog.reject)
    actions.addWidget(close)
    layout.addLayout(actions)
    owner._section_help = dialog
    dialog.show()


def install_help(owner):
    shortcut = QShortcut(QKeySequence.HelpContents, owner)
    shortcut.setContext(Qt.ApplicationShortcut)
    shortcut.activated.connect(lambda: show_context_help(owner))
    owner._help_shortcut = shortcut


def welcome_path(user):
    key = hashlib.sha256(f"{user.id}:{user.username.casefold()}".encode()).hexdigest()[:20]
    return local_state_dir() / ("master_training_" + key + ".json")


def offer_training(owner):
    if sip.isdeleted(owner) or not owner.isVisible() or getattr(owner, "_live_closed", False):
        return
    roles = split_roles(owner.user.role)
    master = any(role == "Мастер" or role in WORKSHOP_ROLES for role in roles)
    if not master or welcome_path(owner.user).exists() or not getattr(owner, "_account_active", True):
        return
    dialog = QDialog(owner)
    dialog.setWindowTitle("Добро пожаловать в Smart Order")
    dialog.setObjectName("MasterWelcome")
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setMinimumWidth(460)
    layout = QVBoxLayout(dialog)
    title = QLabel("Добро пожаловать, мастер!", dialog)
    title.setObjectName("TitleLabel")
    layout.addWidget(title)
    text = QLabel("Желаете пройти обучение работе в программе?\nПокажем только доступные вам действия. Обучение можно повторить через значок руководства рядом с колокольчиком.", dialog)
    text.setWordWrap(True)
    layout.addWidget(text)
    buttons = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No, dialog)
    buttons.button(QDialogButtonBox.Yes).setText("Да, пройти обучение")
    buttons.button(QDialogButtonBox.No).setText("Нет, начать работу")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    def chosen(result):
        welcome_path(owner.user).write_text(json.dumps({"accepted": result == QDialog.Accepted}), encoding="utf-8")
        if result == QDialog.Accepted:
            QTimer.singleShot(0, lambda: start_training(owner))
    dialog.finished.connect(chosen)
    owner._welcome_dialog = dialog
    dialog.show()


def training_steps(user):
    # Deliberately follows a master's daily work, even when an administrator tests it.
    candidates = [
        ("orders", Permission.ORDERS_VIEW, 0, "table-panel", "Ваши наряды", "Здесь находятся наряды выбранного цеха. Дата и фильтры помогают найти нужную смену; черновики отмечены отдельно."),
        ("create", Permission.ORDERS_CREATE, 0, "create", "Начните с создания", "Кнопка «Создать наряд» открывает редактор. Следующие шаги покажут учебный пример."),
        ("details", Permission.ORDERS_CREATE, -1, "OrderInfoGroup", "Укажите смену", "Проверьте дату, тип смены, мастера и подразделение. Комментарий необязателен."),
        ("workers", Permission.ORDERS_CREATE, -1, "add_employee_btn", "Добавьте работников", "Кнопка выбирает работников из справочника. В обычном режиме одна работа назначается выбранной группе."),
        ("works", Permission.ORDERS_CREATE, -1, "table", "Назначьте работы", "Нажмите «Добавить работы» или дважды щёлкните ячейку в столбце «Работы». В режиме «Отдельный работник» используйте кнопку добавления."),
        ("values", Permission.ORDERS_CREATE, -1, "table", "Заполните часы и объёмы", "Введите часы, ФИКС и ФАКТ. Вес и оплата рассчитываются автоматически. Названия работ переносятся по строкам, столбцы подстраиваются под окно."),
        ("save", Permission.ORDERS_CREATE, -1, "button_box", "Сохраните результат", "«Сохранить» записывает наряд и возвращает к списку. Если закрыть новый незавершённый наряд, останется черновик. Учебный пример ничего не сохраняет."),
        ("edit", Permission.ORDERS_EDIT, 0, "edit", "Исправьте сохранённый наряд", "Выберите строку и нажмите «Редактировать». Исходная версия сохраняется в истории."),
        ("editing", Permission.ORDERS_EDIT, -2, "table", "Режим редактирования", "Справа вверху мигает отметка режима. После изменения работ, часов или объёмов кнопка «Сохранить» создаёт новую версию."),
        ("history", Permission.ORDERS_HISTORY, 0, "history-panel", "Кто и что изменил", "Виджет истории показывает автора и время. Нажмите запись: откроются добавленные и удалённые работы, старые и новые значения полей."),
        ("export", Permission.ORDERS_EXPORT, 0, "export-group", "Excel или принтер", "Левая половина сохраняет Excel. Правая открывает системную печать: принтер по умолчанию, Times New Roman 14, все столбцы на странице по ширине."),
        ("people", Permission.EMPLOYEES_VIEW, 2, "people_table", "Справочники вашей смены", "Здесь работники, мастера и подразделения. Поиск помогает найти запись; дата и автор показывают, кто её добавил или изменил."),
        ("notifications", Permission.NOTIFICATIONS_VIEW, 0, "notifications", "Следите за уведомлениями", "Колокольчик сообщает об изменениях и несохранённых черновиках. Нажмите уведомление о черновиках, чтобы перейти к их списку."),
    ]
    return [step for step in candidates if user.can(step[1])]


class CoachOverlay(QFrame):
    def __init__(self, tour, host, title, text, number, total):
        super().__init__(host)
        self.tour, self.host, self.highlight = tour, host, QRect()
        self.setObjectName("TrainingOverlay")
        self.setGeometry(host.rect())
        self.setFocusPolicy(Qt.StrongFocus)
        self.card = QFrame(self)
        self.card.setObjectName("TrainingCard")
        self.card.setStyleSheet("QFrame#TrainingCard{background:#ecf6ff;color:#102b50;border:1px solid #99cafa;border-radius:16px;} QLabel{background:transparent;color:#102b50;border:0;} QPushButton{color:#006ed9;} QPushButton#PrimaryButton{color:white;background:#0785ff;}")
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(22, 18, 22, 18)
        tag = QLabel(f"УЧЕБНЫЙ ПРИМЕР · {number} / {total}", self.card)
        layout.addWidget(tag)
        heading = QLabel(title, self.card)
        heading.setWordWrap(True)
        heading.setStyleSheet("font-size:22px;font-weight:700;")
        layout.addWidget(heading)
        body = QLabel(text, self.card)
        body.setWordWrap(True)
        layout.addWidget(body)
        row = QHBoxLayout()
        stop = QPushButton("Завершить", self.card)
        stop.clicked.connect(tour.finish)
        row.addWidget(stop)
        row.addStretch()
        back = QPushButton("Назад", self.card)
        back.setEnabled(number > 1)
        back.clicked.connect(lambda: tour.advance(-1))
        row.addWidget(back)
        self.next = QPushButton("Готово" if number == total else "Далее", self.card)
        self.next.setObjectName("PrimaryButton")
        self.next.clicked.connect(lambda: tour.advance(1))
        row.addWidget(self.next)
        layout.addLayout(row)
        host.installEventFilter(self)
        self.place_card()
        self.show()
        self.raise_()
        self.next.setFocus()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            self.setGeometry(self.host.rect())
            self.place_card()
        return False

    def place_card(self):
        self.card.setFixedWidth(min(500, max(300, self.width() - 32)))
        self.card.adjustSize()
        x, y = max(16, self.width() - self.card.width() - 24), max(16, self.height() - self.card.height() - 24)
        if self.highlight.intersects(QRect(x, y, self.card.width(), self.card.height())):
            y = 24
        self.card.move(x, y)

    def set_highlight(self, rect):
        self.highlight = rect.intersected(self.rect()).adjusted(-3, -3, 3, 3)
        self.place_card()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        shade = QPainterPath()
        shade.setFillRule(Qt.OddEvenFill)
        shade.addRect(QRectF(self.rect()))
        if not self.highlight.isEmpty():
            shade.addRoundedRect(QRectF(self.highlight), 10, 10)
        painter.fillPath(shade, QColor(5, 20, 38, 175))
        if not self.highlight.isEmpty():
            painter.setPen(QPen(QColor("#60baff"), 2))
            painter.drawRoundedRect(QRectF(self.highlight), 10, 10)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.tour.finish()
        else:
            super().keyPressEvent(event)


class MasterTour(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner, self.position, self.overlay = owner, -1, None
        self.original_tab = owner.tabs.currentIndex()
        self.editor = None
        self.editor_mode = None
        self.temp = None
        self.running = True
        owner.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Close:
            self.finish()
        return False

    def demo_editor(self, editing):
        if self.editor is not None and self.editor_mode == editing:
            return self.editor
        if self.editor is not None:
            self.editor.reject()
            self.editor.deleteLater()
        from .db import Database
        from .domain import OrderLine
        from .heavy_ui import HeavyWorkOrderDialog
        from .security import SessionUser, ALL_PERMISSIONS
        if self.temp is None:
            self.temp = tempfile.TemporaryDirectory(prefix="smartorder-training-")
            self.demo_db = Database(Path(self.temp.name) / "demo.db")
            actor = SessionUser(-1, "Учебный мастер", "Администратор", frozenset(ALL_PERMISSIONS))
            db = self.demo_db
            worker = db.add_employee(actor, "Иванов Иван · учебный пример")
            master = db.add_employee(actor, "Учебный мастер", True)
            department = db.add_department(actor, "Учебное подразделение")
            work = db.add_work_type(actor, "Упаковка готовой продукции по сменному заданию", "0000001", "2")
            line = OrderLine(worker, "Иванов Иван · учебный пример", work, "Упаковка готовой продукции по сменному заданию", "0000001", Decimal(2), Decimal(8), Decimal(10), Decimal(2))
            identity = db.save_order(actor, date.today().strftime("%d-%m-%Y"), "Дневная", master, department, [line])
            self.demo_order = db.get_order(identity)
        class DemoEditor(HeavyWorkOrderDialog):
            def _save_draft(self):
                pass
            def _accept(self):
                pass
        self.editor = DemoEditor(self.demo_db, self.owner.user, self.demo_order if editing else None, parent=self.owner)
        self.editor.setObjectName("TrainingOrderEditor")
        self.editor.setWindowTitle("Учебный пример · " + ("Редактирование" if editing else "Создание наряда"))
        if not editing:
            self.editor._load_order(self.demo_order)
        self.editor_mode = editing
        self.editor.show()
        return self.editor

    def advance(self, direction=1):
        if not self.running:
            return
        if not help_allowed(self.owner.user) or not getattr(self.owner, "_account_active", True):
            self.finish()
            return
        steps = training_steps(self.owner.user)
        self.position += direction
        if not 0 <= self.position < len(steps):
            self.finish()
            return
        if self.overlay is not None:
            self.overlay.hide()
            self.overlay.deleteLater()
        key, permission, tab, target, title, text = steps[self.position]
        if tab < 0:
            host = self.demo_editor(tab == -2)
        else:
            if self.editor is not None:
                self.editor.hide()
            self.owner.tabs.setCurrentIndex(tab)
            host = self.owner
        self.overlay = CoachOverlay(self, host, title, text, self.position + 1, len(steps))
        overlay = self.overlay
        def highlight():
            if not self.running or self.overlay is not overlay:
                return
            if tab == 0 and getattr(self.owner, "_glass_ready", False):
                script = '(function(){var e=document.getElementById(' + json.dumps(target) + ');if(!e)return null;var r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height];})()'
                def found(bounds):
                    if bounds and self.running and self.overlay is overlay:
                        origin = self.owner._glass.mapTo(host, QPoint(0, 0))
                        overlay.set_highlight(QRect(origin.x() + int(bounds[0]), origin.y() + int(bounds[1]), int(bounds[2]), int(bounds[3])))
                self.owner._glass.page().runJavaScript(script, found)
            else:
                native = {"table-panel": "orders_table", "create": "create_order_btn", "edit": "edit_order_btn", "history-panel": "info_users_list", "export-group": "export_actions", "notifications": "titlebar"}.get(target, target)
                widget = getattr(host, native, None) or host.findChild(QFrame, target)
                if widget is None and target == "OrderInfoGroup":
                    widget = host.order_date.parentWidget()
                if widget is not None:
                    overlay.set_highlight(QRect(widget.mapTo(host, QPoint(0, 0)), widget.size()))
        QTimer.singleShot(80, highlight)

    def finish(self):
        if not self.running:
            return
        self.running = False
        if self.overlay is not None:
            self.overlay.hide()
            self.overlay.deleteLater()
        if self.editor is not None:
            self.editor.reject()
            self.editor.deleteLater()
        if self.temp is not None:
            self.temp.cleanup()
        if self.owner.tabs.isTabEnabled(self.original_tab):
            self.owner.tabs.setCurrentIndex(self.original_tab)
        self.owner._master_tour = None
        self.deleteLater()


def start_training(owner):
    if not help_allowed(owner.user):
        return
    old = getattr(owner, "_master_tour", None)
    if old is not None:
        old.finish()
    owner._master_tour = MasterTour(owner)
    owner._master_tour.advance()

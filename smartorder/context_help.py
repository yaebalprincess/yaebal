"""Section help and a permission-aware tour using disposable demonstration data."""
import hashlib
import json
from html import escape

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout,
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
    from .help_surface import opaque_help, center_dialog
    ink=opaque_help(dialog,owner.ui_settings.theme)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setObjectName("SectionHelp")
    dialog.setWindowTitle("Справка · " + title)
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.resize(820, 620)
    layout = QVBoxLayout(dialog)
    browser = QTextBrowser(dialog)
    browser.document().setDefaultStyleSheet("body{color:"+ink+";} h1{font-size:24px;} p{font-size:14px;}")
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
    center_dialog(dialog,owner,(820,620))
    dialog.show()


def show_training_start(owner):
    if not help_allowed(owner.user) or not getattr(owner,"_account_active",True):return
    old=getattr(owner,"_master_tour",None)
    if old is not None:old.finish()
    from .help_surface import opaque_help,center_dialog
    dialog=QDialog(owner)
    opaque_help(dialog,owner.ui_settings.theme)
    dialog.setObjectName("TrainingStart")
    dialog.setWindowTitle("Обучение: как работать с нарядами?")
    dialog.setWindowModality(Qt.WindowModal)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setFixedWidth(540)
    layout=QVBoxLayout(dialog);layout.setContentsMargins(24,22,24,22);layout.setSpacing(16)
    title=QLabel("Обучение: как работать с нарядами?",dialog)
    title.setObjectName("TrainingTitle");title.setWordWrap(True);title.setAlignment(Qt.AlignCenter);layout.addWidget(title)
    text=QLabel("Будем идти по шагам: нажимайте на подсвеченные элементы. Покажем создание и редактирование наряда, историю и доступные мастеру функции администрирования. Учебные данные не попадут в рабочую базу.",dialog)
    text.setWordWrap(True);layout.addWidget(text)
    start=QPushButton("Начать!",dialog);start.setObjectName("PrimaryButton");start.setMinimumHeight(38)
    start.clicked.connect(lambda:(dialog.accept(),start_training(owner)));layout.addWidget(start)
    row=QHBoxLayout()
    section=QPushButton("Справка по разделу (F1)",dialog);section.clicked.connect(lambda:(dialog.accept(),show_context_help(owner)));row.addWidget(section)
    full=QPushButton("Полное руководство",dialog);full.clicked.connect(owner._open_guide);row.addWidget(full);layout.addLayout(row)
    owner._training_start=dialog
    center_dialog(dialog,owner);dialog.show()


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
    from .help_surface import opaque_help, center_dialog
    opaque_help(dialog,owner.ui_settings.theme)
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
    center_dialog(dialog,owner)
    dialog.show()


def training_steps(user):
    from .guided_training import lesson_keys
    return lesson_keys(user)


def start_training(owner):
    if not help_allowed(owner.user):return
    from .guided_training import GuidedTour
    old=getattr(owner,"_master_tour",None)
    if old is not None:old.finish()
    owner._master_tour=GuidedTour(owner)
    owner._master_tour.begin()

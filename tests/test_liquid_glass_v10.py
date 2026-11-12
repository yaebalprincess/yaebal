"""Release checks for editor geometry, revision details, reference authors and training."""
from copy import deepcopy
from datetime import date
from decimal import Decimal

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QFontMetrics, QMouseEvent
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QTextBrowser

from smartorder import heavy_ui
from smartorder.config import SettingsStore, local_drafts_dir
from smartorder.domain import OrderLine
from smartorder.security import Permission
from test_liquid_glass import app, drain, glass, javascript, populate, system
from test_rc19_workshops_analytics import order


def close_editor(dialog, app):
    dialog.reject()
    dialog.deleteLater()
    app.processEvents()


def test_editor_columns_wrap_fit_and_persist_across_orders(glass, app):
    owner, manager, admin = glass
    db, identity, *_ = populate(app, glass)
    saved = db.get_order(identity)
    dialog = heavy_ui.HeavyWorkOrderDialog(db, admin, saved, parent=owner)
    dialog.show()
    drain(app, lambda: not dialog.editor_columns.fit_timer.isActive() and not dialog.editor_columns.rows_timer.isActive())
    table, layout = dialog.table, dialog.editor_columns
    assert table.wordWrap() and table.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert table.horizontalHeader().length() <= table.viewport().width() + 2
    assert table.horizontalHeader().sectionViewportPosition(10) + table.columnWidth(10) >= table.viewport().width() - 2
    assert table.columnWidth(3) >= QFontMetrics(layout.code_font).horizontalAdvance("1234567")
    table.item(0, 2).setText("Очень длинное наименование работы по упаковке готовой продукции за смену " * 4)
    drain(app, lambda: not layout.rows_timer.isActive())
    assert table.rowHeight(0) > table.fontMetrics().height() * 2
    header = table.horizontalHeader()
    point = QPoint(header.sectionViewportPosition(2) + header.sectionSize(2) - 1, header.height() // 2)
    previous = header.sectionSize(2)
    QTest.mousePress(header.viewport(), Qt.LeftButton, pos=point)
    moved = point + QPoint(55, 0)
    QApplication.sendEvent(header.viewport(), QMouseEvent(QEvent.MouseMove, QPointF(moved),
                          QPointF(header.viewport().mapToGlobal(moved)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(header.viewport(), Qt.LeftButton, pos=point + QPoint(55, 0))
    drain(app, lambda: not layout.fit_timer.isActive())
    assert header.sectionSize(2) != previous
    assert header.length() <= table.viewport().width() + 2
    weights = list(layout.weights)
    close_editor(dialog, app)
    assert SettingsStore(admin.id, admin.username).load().editor_column_weights == weights
    another = heavy_ui.HeavyWorkOrderDialog(db, admin, saved, parent=owner)
    another.show()
    drain(app, lambda: not another.editor_columns.fit_timer.isActive())
    assert another.editor_columns.weights == weights
    close_editor(another, app)


def test_work_double_click_uses_picker_except_separate_worker(glass, app, monkeypatch):
    owner, manager, admin = glass
    db, identity, *_ = populate(app, glass)
    dialog = heavy_ui.HeavyWorkOrderDialog(db, admin, db.get_order(identity), parent=owner)
    dialog.show()
    drain(app, lambda: not dialog.editor_columns.fit_timer.isActive())
    called = []
    monkeypatch.setattr(dialog, "_add_works", lambda: called.append(dialog.table.currentRow()))
    target = dialog.table.visualItemRect(dialog.table.item(0, 2)).center()
    QTest.mouseClick(dialog.table.viewport(), Qt.LeftButton, pos=target)
    QTest.mouseDClick(dialog.table.viewport(), Qt.LeftButton, pos=target)
    assert called == [0]
    dialog.separate_worker_check.setChecked(True)
    QTest.mouseDClick(dialog.table.viewport(), Qt.LeftButton, pos=target)
    assert called == [0]
    close_editor(dialog, app)


def test_reference_dates_keep_creation_and_edit_authors_and_imports(system):
    manager, admin = system
    manager.auth.add_user(admin, "editor", "password123", "Администратор")
    editor = manager.auth.authenticate("editor", "password123")
    db = manager.database("packaging", admin)
    work = db.add_work_type(admin, "Работа", "1234567", "2")
    person = db.add_employee(admin, "Работник")
    master = db.add_employee(admin, "Мастер", True)
    department = db.add_department(admin, "Подразделение")
    db.update_work_type(editor, work, "Работа новая", "1234567", "3")
    db.update_employee(editor, person, "Работник новый")
    db.update_employee(editor, master, "Мастер новый")
    db.update_department(editor, department, "Подразделение новое")
    for kind, identity in (("work_type", work), ("employee", person), ("employee", master), ("department", department)):
        assert db.reference_audit(kind)[identity] == ("admin", "editor")
    db.import_work_types(editor, [("Импорт", "7654321", 1)])
    db.import_people(editor, ["Импорт работника"], False)
    db.import_departments(editor, ["Импорт отдела"])
    assert ("editor", "") in db.reference_audit("work_type").values()
    assert ("editor", "") in db.reference_audit("employee").values()
    assert ("editor", "") in db.reference_audit("department").values()
    assert len(db.get_work_types()[0]) == 7 and len(db.get_employees()[0]) == 5


def test_reference_cells_show_date_and_actor_for_all_modes(glass, app):
    owner, manager, admin = glass
    db, *_ = populate(app, glass)
    from smartorder.reference_audit_ui import AUTHOR_ROLE, DATE_ROLE
    owner.tabs.setCurrentIndex(1)
    drain(app, lambda: hasattr(owner, "work_table") and owner.work_table.rowCount() == 1)
    assert owner.work_table.columnCount() == 5
    assert owner.work_table.horizontalHeaderItem(4).text() == "Дата редактирования"
    assert owner.work_table.item(0, 3).data(AUTHOR_ROLE) == "admin"
    assert owner.work_table.item(0, 3).data(DATE_ROLE)
    owner.tabs.setCurrentIndex(2)
    drain(app, lambda: hasattr(owner, "people_table") and owner.people_table.rowCount() > 0)
    assert owner.people_table.item(0, 1).data(AUTHOR_ROLE) == "admin"
    assert owner.people_table.rowHeight(0) >= 58


def test_history_popup_contains_actor_work_time_and_changed_values(glass, app):
    owner, manager, admin = glass
    db, identity, line, master, department = populate(app, glass)
    manager.auth.add_user(admin, "chief", "password123", "Администратор")
    chief = manager.auth.authenticate("chief", "password123")
    line.hours, line.fixed_boxes = Decimal(9), Decimal(15)
    changed = db.save_order(chief, date.today().strftime("%d-%m-%Y"), "Дневная", master, department, [line], parent_id=identity)
    from smartorder.order_history import history_html, line_changes
    html = history_html(db, changed, changed)
    assert "chief" in html and "Работа packaging" in html and "Часы" in html
    assert "8 → <b>9" in html and "10 → <b>15" in html
    assert db.get_order(changed)["info"]["edit_date"] in html
    duplicate = deepcopy(line)
    assert line_changes([line, duplicate], [duplicate, line]) == []
    owner.refresh_orders()
    drain(app, lambda: not owner._orders_running)
    owner.orders_table.selectRow(0)
    drain(app, lambda: owner.info_users_list.count() == 2)
    owner._show_history_details(owner.info_users_list.item(1))
    drain(app, lambda: getattr(owner, "_history_details_dialog", None) is not None)
    dialog = owner._history_details_dialog
    assert "chief" in dialog.findChild(QTextBrowser).toPlainText()
    dialog.reject()


def test_print_pdf_fits_columns_and_keeps_fourteen_point_type(system, app, tmp_path):
    import fitz
    from smartorder.order_printing import configure_printer, print_document
    manager, admin = system
    db, identity, *_ = order(manager, admin, "packaging")
    saved = db.get_order(identity)
    saved["lines"] = [deepcopy(saved["lines"][0]) for _ in range(36)]
    document = print_document(saved)
    assert document.defaultFont().family() == "Times New Roman"
    assert document.defaultFont().pointSize() == 14
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(tmp_path / "order.pdf"))
    configure_printer(printer)
    document.print_(printer)
    pdf = fitz.open(tmp_path / "order.pdf")
    assert len(pdf) >= 2
    text = "".join(page.get_text() for page in pdf)
    assert "ИТОГО" in text and "001" in text
    for page in pdf:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    assert span["bbox"][2] <= page.rect.width + 1
                    assert span["size"] >= 13.9


def test_print_dialog_keeps_native_window_and_selected_order(glass, app, monkeypatch):
    from PyQt5.QtPrintSupport import QPrintDialog, QPageSetupDialog
    from smartorder import order_printing
    owner, manager, admin = glass
    db, identity, *_ = populate(app, glass)
    printer = QPrinter()
    for kind in (QPrintDialog, QPageSetupDialog):
        dialog = kind(printer, owner)
        dialog.ensurePolished()
        assert not dialog.property("glassOverlay")
        assert not dialog.windowFlags() & Qt.FramelessWindowHint
        assert not dialog.testAttribute(Qt.WA_TranslucentBackground)
        dialog.deleteLater()
    printed = []
    monkeypatch.setattr(order_printing, "request_print", lambda saved, parent: printed.append(saved))
    owner.orders_table.selectRow(0)
    owner._publish_glass_state(force=True)
    drain(app, lambda: not javascript(app, owner, 'document.getElementById("print").disabled'))
    javascript(app, owner, 'document.getElementById("print").click()')
    drain(app, lambda: len(printed) == 1)
    assert printed[0]["info"]["id"] == identity
    widths = javascript(app, owner, '["export","print"].map(id=>document.getElementById(id).getBoundingClientRect().width)')
    assert abs(widths[0] - widths[1]) <= 1


def test_help_icon_context_and_master_only_tour(glass, app):
    from smartorder.context_help import show_context_help, start_training, training_steps, help_allowed
    from smartorder.security import SessionUser, DEFAULT_ROLE_PERMISSIONS
    owner, manager, admin = glass
    assert javascript(app, owner, '!document.getElementById("help").hidden')
    owner.tabs.setCurrentIndex(2)
    drain(app, lambda: hasattr(owner, "people_table"))
    show_context_help(owner)
    assert "Сотрудники" in owner._section_help.windowTitle()
    owner._section_help.reject()
    assert not help_allowed(SessionUser(5, "economist", "Экономист", frozenset()))
    master = SessionUser(9, "master", "Мастер Упаковка", frozenset(DEFAULT_ROLE_PERMISSIONS["Мастер Упаковка"]))
    assert help_allowed(master)
    assert "administration" in training_steps(master)
    assert not {"catalog","analytics"}.intersection(training_steps(master))
    before = len(manager.database("packaging", admin).list_orders())
    start_training(owner)
    tour = owner._master_tour
    assert tour.key=="create"
    tour.finish()
    assert owner._master_tour is None
    assert len(manager.database("packaging", admin).list_orders()) == before
    assert not list(local_drafts_dir().rglob("*.json"))
    assert not list(manager.root.rglob("new_order*.json"))


def test_master_welcome_choice_is_once_per_account(system, app):
    from smartorder.enterprise_ui import MainWindow
    from smartorder.context_help import offer_training, welcome_path
    manager, admin = system
    manager.auth.add_user(admin, "master", "password123", "Мастер Упаковка")
    master = manager.auth.authenticate("master", "password123")
    owner = MainWindow(manager.database("packaging", master), master, manager)
    owner.show()
    offer_training(owner)
    welcome = owner._welcome_dialog
    assert welcome.isVisible() and not welcome_path(master).exists()
    buttons = welcome.findChild(QDialogButtonBox)
    buttons.button(QDialogButtonBox.No).click()
    assert welcome_path(master).exists()
    offer_training(owner)
    assert owner._welcome_dialog is welcome
    welcome_path(master).unlink()
    offer_training(owner)
    owner._welcome_dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Yes).click()
    drain(app, lambda: getattr(owner, "_master_tour", None) is not None)
    tour = owner._master_tour
    assert tour.key=="create"
    tour.finish()
    assert manager.database("packaging", master).list_orders() == []
    owner._rc4_exit_confirmed = True
    owner.close()
    owner.deleteLater()
    app.processEvents()

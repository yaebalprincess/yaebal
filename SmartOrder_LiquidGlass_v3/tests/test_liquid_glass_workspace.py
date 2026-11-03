"""Exercise real controllers, nested dialogs and native glass rendering."""
from datetime import date
from decimal import Decimal

from PyQt5.QtCore import QDate, QEvent, QPoint, Qt, QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QTextBrowser

from smartorder import heavy_ui
from smartorder.heavy_ui import (WorkOrderDialog, EmployeeSelectionDialog,
    WorkSelectionDialog, DateRangeDialog)
from smartorder.liquid_effects import ControlLight, GlassBackdrop, PageTransition
from smartorder.news_ui import NewsDialog
from test_liquid_glass import app, system, glass, javascript, drain, populate


def dispose(app, dialog):
    dialog.close()
    dialog.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def test_all_tabs_share_wallpaper_theme_and_readable_native_controls(glass, app):
    window, _, _ = glass
    for dark in (False, True):
        window.theme.setChecked(dark)
        for index in range(1, 6):
            window.tabs.setCurrentIndex(index)
            app.processEvents()
            host = window.tabs.currentWidget()
            expected = "dark" if dark else "light"
            assert window._legacy_shell._liquid_backdrop.isVisible()
            assert host.property("theme") == expected
            assert all(button.property("theme") == expected for button in host.findChildren(QPushButton))
            assert all("background:transparent;border:none;" != button.styleSheet() for button in host.findChildren(QPushButton))
    window.tabs.setCurrentIndex(5)
    labels = [label.text() for label in window.tabs.currentWidget().findChildren(QLabel)]
    buttons = [button.text() for button in window.tabs.currentWidget().findChildren(QPushButton)]
    assert "Smart Order" in labels and "Enterprise Edition" in labels
    assert "Новости обновлений" in buttons and "Скачать руководство в PDF" in buttons
    footer = window.tabs.currentWidget().findChild(QTextBrowser, "AboutFooter")
    assert footer.document().find("tmbsir").charFormat().fontUnderline()


def test_real_create_button_saves_validated_order_with_calculations(glass, app, monkeypatch):
    window, _, _ = glass
    db, _, line, master, department = populate(app, glass)
    notices, failures, seen = [], [], []
    monkeypatch.setattr(heavy_ui, "info", lambda *args: notices.append(args[2]))
    monkeypatch.setattr(heavy_ui, "error", lambda *args: failures.append(str(args[2])))

    def fill_editor():
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, WorkOrderDialog):
            QTimer.singleShot(30, fill_editor)
            return
        seen.append(dialog)
        try:
            assert dialog._liquid_backdrop.isVisible()
            assert dialog.windowOpacity() == 1
            payload = {"order_date": date.today().strftime("%d-%m-%Y"),
                       "shift_type": "Дневная", "master_id": master,
                       "department_id": department, "comment": "Liquid Glass scenario",
                       "lines": [{"employee_id": line.employee_id,
                                  "employee_name": line.employee_name,
                                  "work_type_id": line.work_type_id, "work_name": line.work_name,
                                  "work_code": line.work_code, "price": "2", "hours": "8",
                                  "fixed_boxes": "12", "fixed_weight": "3"}]}
            dialog.load_draft_payload(payload)
            assert dialog._validate() is None
            assert dialog.get_data()["lines"][0].fixed_payment == Decimal("72")
            dialog._accept()
        except Exception as exc:
            failures.append(repr(exc))
            dialog.reject()

    QTimer.singleShot(40, fill_editor)
    javascript(app, window, 'document.getElementById("create").click()')
    drain(app, lambda: bool(notices) or bool(failures), timeout=10)
    assert seen and not failures
    drain(app, lambda: not window._orders_running and window.orders_table.rowCount() == 2)
    new = next(row for row in db.list_orders() if db.get_order(row[0])["info"]["comment"] == "Liquid Glass scenario")
    stored = db.get_order(new[0])
    assert stored["lines"][0].fixed_payment == Decimal("72")


def test_nested_picklists_calendar_news_and_editor_have_glass_without_fading_text(glass, app, tmp_path):
    window, _, _ = glass
    populate(app, glass)
    for dark in (False, True):
        window.theme.setChecked(dark)
        dialogs = [WorkOrderDialog(window.db, window.user, parent=window),
                   EmployeeSelectionDialog(window.db, window),
                   WorkSelectionDialog(window.db, window),
                   DateRangeDialog(QDate.currentDate(), QDate.currentDate(), window),
                   NewsDialog(window, tmp_path / "news.txt")]
        for dialog in dialogs:
            dialog.show()
            app.processEvents()
            assert dialog._liquid_backdrop.isVisible()
            assert dialog.property("theme") == ("dark" if dark else "light")
            assert dialog.windowOpacity() == 1.0
            assert dialog._liquid_backdrop.testAttribute(Qt.WA_TransparentForMouseEvents)
            dispose(app, dialog)


def test_cursor_lens_ripple_keyboard_and_idle_timer_preserve_button_geometry(glass, app):
    window, _, _ = glass
    window.tabs.setCurrentIndex(5)
    button = next(b for b in window.tabs.currentWidget().findChildren(QPushButton) if b.text() == "Как работать в программе?")
    original = button.geometry()
    app.sendEvent(button, QEvent(QEvent.Enter))
    QTest.mouseMove(button, QPoint(8, 8))
    controller = app._smartorder_liquid
    light = controller.lights[button]
    drain(app, lambda: light.amount > .5)
    QTest.mousePress(button, Qt.LeftButton, pos=QPoint(8, 8))
    assert light.ripples
    # Send the release outside: test the animation without opening a guide.
    QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(-5, -5))
    assert light.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert button.geometry() == original
    app.sendEvent(button, QEvent(QEvent.Leave))
    drain(app, lambda: not light.ripples and light.amount == 0)
    drain(app, lambda: not controller.timer.isActive())


def test_tab_switch_does_not_allocate_duplicate_backgrounds_or_effects(glass, app):
    window, _, _ = glass
    for _ in range(3):
        for index in (1, 2, 3, 4, 5, 0):
            window.tabs.setCurrentIndex(index)
            app.processEvents()
    drain(app, lambda: not app._smartorder_liquid.timer.isActive())
    assert len(window._legacy_shell.findChildren(GlassBackdrop)) == 1
    assert not [w for w in window._glass_stack.findChildren(PageTransition) if w.isVisible()]

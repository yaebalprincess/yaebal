"""The editor, notification workflow and display regressions from v9."""
import json

from PyQt5 import sip
from PyQt5.QtCore import QDate, QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtWidgets import QApplication, QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QLabel, QPushButton, QToolButton

from smartorder import heavy_ui
from smartorder.config import local_drafts_dir
from smartorder.desktop_live import drafts_folder
from smartorder.glass_ui import MainWindow, row_key
from test_liquid_glass import app, drain, glass, javascript, populate, system


def test_edit_action_opens_current_editor_and_saves_revision(glass, app, monkeypatch):
    window, _, user = glass
    db, order_id, *_ = populate(app, glass)
    errors = []
    monkeypatch.setattr(heavy_ui, "warn", lambda *args: errors.append(args[2:]))
    monkeypatch.setattr(heavy_ui, "error", lambda *args: errors.append(args[2:]))
    monkeypatch.setattr(heavy_ui, "info", lambda *args: None)

    def edit(dialog):
        dialog.show()
        app.processEvents()
        assert dialog.order_id == order_id and dialog.lock_token
        assert dialog._aligned_footer and dialog.table.isColumnHidden(8)
        assert not dialog.has_changes()
        label = dialog._glass_chrome.findChild(QLabel, "EditModeLabel")
        assert label.isVisible() and label.text() == "В режиме редактирования"
        assert dialog._edit_banner_anim.loopCount() == -1
        dialog.separate_worker_check.toggle()
        assert dialog.has_changes()
        dialog.comment.setText("Проверка редактора")
        dialog.button_box.button(QDialogButtonBox.Ok).click()
        return dialog.result()

    monkeypatch.setattr(heavy_ui.WorkOrderDialog, "exec_", edit)
    window._glass_command("edit", {"key": f"order:{order_id}"})
    assert not errors
    latest = db.get_order(db.order_history(order_id)[0]["id"])
    assert latest["info"]["id"] != order_id
    assert latest["info"]["comment"] == "Проверка редактора"
    token, _ = db.acquire_edit_lock(order_id, user)
    assert token
    db.release_edit_lock(order_id, token)


def test_draft_notice_dismissal_and_new_count_survive_restart(system, app, monkeypatch):
    manager, user = system

    def draft(key, index, owner=None, local=False):
        folder = local_drafts_dir(key) if local else drafts_folder(manager.root, key)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"new_order_{user.id}_test_{index}.json"
        data = {"order_date": "01-01-2025", "shift_type": "Дневная", "draft_owner_id": user.id if owner is None else owner,
                "draft_owner_username": user.username, "lines": [{"employee_name": "Демо"}]}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    for index in range(4):
        draft("packaging" if index < 2 else "smoking", index)
    draft("packaging", 0, local=True)  # Same draft in the fallback folder.
    draft("packaging", 9, owner=user.id + 1)

    windows = []

    def launch():
        window = MainWindow(manager._databases["packaging"], user, manager)
        windows.append(window)
        window.resize(1400, 850)
        window.show()
        drain(app, lambda: window._glass_painted and len(window._draft_keys) >= 4, timeout=12)
        return window

    def close(window):
        window._rc4_exit_confirmed = True
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    try:
        first = launch()
        first.show_notifications()
        popup = first.notification_popup
        assert popup.findChild(QPushButton, "OpenDraftNotice").text().endswith("×4")
        popup.findChild(QToolButton, "DismissDraftNotice").click()
        assert not any(item.get("kind") == "drafts" for item in first._notification_items)
        close(first)

        second = launch()
        assert not any(item.get("kind") == "drafts" for item in second._notification_items)
        editor = heavy_ui.WorkOrderDialog(second.db, user, parent=second)
        editor.load_draft_payload({"order_date": "01-01-2025", "lines": [{"employee_name": "Новый черновик"}]})
        editor.reject()
        editor.deleteLater()
        close(second)

        third = launch()
        third.show_notifications()
        popup = third.notification_popup
        entry = popup.findChild(QPushButton, "OpenDraftNotice")
        assert entry.text().endswith("×5")
        entry.click()
        assert not popup.isVisible()
        drain(app, lambda: third.orders_table.rowCount() == 5 and not third._orders_running)
        assert all(row[7] for row in third.orders_table.report_model.rows)
        assert {row[1].split(" · ", 1)[1] for row in third.orders_table.report_model.rows} == {"Упаковка", "Коптильный"}
        drain(app, lambda: javascript(app, third, 'document.getElementById("drafts-bar").hidden') is False)
        javascript(app, third, 'document.getElementById("all-orders").click()')
        drain(app, lambda: not third._draft_view and not third._orders_running)
        third.show_draft_list()
        drain(app, lambda: third.orders_table.rowCount() == 5 and not third._orders_running)
        foreign = next(row for row in third.orders_table.report_model.rows if row[1] == "Черновик · Коптильный")
        opened = []
        def observe(dialog):
            opened.append(dialog.db.workshop)
            return QDialog.Rejected
        monkeypatch.setattr(heavy_ui.WorkOrderDialog, "exec_", observe)
        third._glass_command("edit", {"key": row_key(foreign[0])})
        drain(app, lambda: opened == ["smoking"], timeout=10)
    finally:
        for window in windows:
            if not sip.isdeleted(window):
                close(window)


def test_light_range_calendar_has_light_cells(glass, app):
    window, _, _ = glass
    window.tabs.setCurrentIndex(4)
    dialog = heavy_ui.DateRangeDialog(QDate(2026, 11, 4), QDate(2026, 11, 5), window)
    dialog.show()
    app.processEvents()
    try:
        grid = dialog.calendar.findChild(QAbstractItemView, "qt_calendar_calendarview")
        image = grid.viewport().grab().toImage()
        samples = [image.pixelColor(x, y) for x in range(4, image.width(), 10) for y in range(4, image.height(), 10)]
        assert samples and sum(color.lightness() > 180 for color in samples) > len(samples) * .85
        assert dialog.selected_range() == (QDate(2026, 11, 4), QDate(2026, 11, 5))
    finally:
        dialog.hide()
        dialog.deleteLater()


def test_file_picker_and_font_size_wheel(glass, app):
    window, _, _ = glass
    assert not QApplication.testAttribute(Qt.AA_DontUseNativeDialogs)
    picker = QFileDialog(window)
    picker.ensurePolished()
    assert not picker.property("glassOverlay")
    picker.deleteLater()
    window.tabs.setCurrentIndex(5)
    size = window.appearance_panel.font_controls["body"][1]
    size.setFocus()
    original = size.value()
    wheel = QWheelEvent(QPointF(8, 8), QPointF(size.mapToGlobal(QPoint(8, 8))), QPoint(), QPoint(0, 120),
                        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(size, wheel)
    assert size.value() == original
    size.stepUp()
    assert size.value() > original

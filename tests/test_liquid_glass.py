"""Exercise the real Chromium page, Qt bridge and authoritative order model."""
import json
from datetime import date

import pytest
from PyQt5.QtCore import QDate, QEvent, Qt, QUrl
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5 import sip

QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

from smartorder.glass_ui import MainWindow, ASSET_ROOT, LocalAssetsOnly, row_key
from smartorder.security import Permission
from test_rc19_ui import app, drain
from test_rc19_workshops_analytics import system, order


def javascript(app, window, expression):
    result = []
    window._glass.page().runJavaScript(expression, result.append)
    drain(app, lambda: bool(result), timeout=8)
    return result[0]


@pytest.fixture
def glass(app, system):
    manager, admin = system
    window = MainWindow(manager._databases["packaging"], admin, manager)
    window.resize(1727, 910)
    window.show()
    try:
        drain(app, lambda: window._glass_ready and not window._orders_running, timeout=12)
        yield window, manager, admin
    finally:
        if not sip.isdeleted(window):
            window._rc4_exit_confirmed = True
            window.close()
            window.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


def populate(app, glass):
    window, manager, admin = glass
    db, ident, line, master, department = order(
        manager, admin, "packaging", day=date.today().strftime("%d-%m-%Y"))
    window._refresh_reference_filters()
    window.refresh_orders()
    drain(app, lambda: window.orders_table.rowCount() == 1 and not window._orders_running)
    window._publish_glass_state(force=True)
    drain(app, lambda: javascript(app, window, 'document.querySelectorAll("#order-rows tr").length') == 1)
    return db, ident, line, master, department


def test_real_page_empty_table_and_local_glass_material(glass, app):
    window, _, _ = glass
    assert window._glass_stack.currentWidget() is window._glass
    assert javascript(app, window, 'document.querySelectorAll("#tabs button").length') == 7
    assert javascript(app, window, 'document.querySelectorAll("#order-rows tr").length') == 0
    assert javascript(app, window, 'document.getElementById("account-label").textContent') == "admin · Упаковка"
    assert javascript(app, window, 'CSS.supports("backdrop-filter", "blur(20px)")') is True
    assert javascript(app, window, 'getComputedStyle(document.getElementById("app-shell")).backgroundImage') == "none"
    assert window._legacy_shell._liquid_backdrop.isVisible()
    assert javascript(app, window, 'document.getElementById("edit").disabled') is True


def test_click_uses_existing_create_handler(glass, app, monkeypatch):
    window, _, _ = glass
    called = []
    monkeypatch.setattr(window, "create_order", lambda: called.append("create"))
    javascript(app, window, 'document.getElementById("create").click()')
    drain(app, lambda: called == ["create"])


def test_selection_history_edit_and_excel_use_real_order_id(glass, app, monkeypatch):
    window, _, _ = glass
    _, ident, *_ = populate(app, glass)
    javascript(app, window, 'document.querySelector("#order-rows tr").click()')
    drain(app, lambda: window._selected_ref() == ident and window.info_users_list.count() == 1)
    window._publish_glass_state(force=True)
    drain(app, lambda: not javascript(app, window, 'document.getElementById("edit").disabled'))
    assert javascript(app, window, 'document.querySelectorAll("#history li").length') == 1
    called = []
    monkeypatch.setattr(window, "edit_order", lambda: called.append(("edit", window._selected_ref())))
    monkeypatch.setattr(window, "export_order", lambda: called.append(("export", window._selected_ref())))
    javascript(app, window, 'document.getElementById("edit").click()')
    drain(app, lambda: len(called) == 1)
    drain(app, lambda: not javascript(app, window, 'document.getElementById("export").disabled'))
    javascript(app, window, 'document.getElementById("export").click()')
    drain(app, lambda: len(called) == 2)
    assert called == [("edit", ident), ("export", ident)]


def test_filter_change_is_applied_to_native_query(glass, app):
    window, _, _ = glass
    _, _, _, master, _ = populate(app, glass)
    javascript(app, window, '{const s=document.getElementById("shift");s.value="Ночная";s.dispatchEvent(new Event("change",{bubbles:true}));}')
    drain(app, lambda: window.order_filter_shift.currentText() == "Ночная" and not window._orders_running)
    assert window.orders_table.rowCount() == 0
    javascript(app, window, '{const s=document.getElementById("shift");s.value="Все смены";s.dispatchEvent(new Event("change",{bubbles:true}));}')
    drain(app, lambda: window.order_filter_shift.currentText() == "Все смены" and window.orders_table.rowCount() == 1)
    window._glass_command("filter", {"name": "master", "value": master})
    assert window.order_filter_master.currentData() == master
    window._glass_command("filter", {"name": "master", "value": "../../anything"})
    assert window.order_filter_master.currentData() == master


def test_date_button_preserves_native_date_range_picker(glass, app, monkeypatch):
    window, _, _ = glass
    from smartorder import glass_ui
    class Picker:
        def __init__(self, start, end, parent):
            assert parent is window and start.isValid() and end.isValid()
        def exec_(self): return 1
        def selected_range(self): return QDate(2026, 10, 1), QDate(2026, 10, 29)
    monkeypatch.setattr(glass_ui, "DateRangeDialog", Picker)
    window._glass_command("date", {})
    drain(app, lambda: window.order_filter_date.startDate() == QDate(2026, 10, 1))
    assert window.order_filter_date.endDate() == QDate(2026, 10, 29)


def test_theme_and_zoom_round_trip_and_native_tabs(glass, app):
    window, _, _ = glass
    javascript(app, window, 'document.getElementById("theme").click()')
    drain(app, lambda: window.ui_settings.theme == "dark")
    javascript(app, window, 'const z=document.getElementById("zoom");z.value=150;z.dispatchEvent(new Event("change",{bubbles:true}));')
    drain(app, lambda: window.ui_settings.zoom == 150 and not window._rc18_zoom_timer.isActive())
    assert window.settings_store.load().zoom == 150
    javascript(app, window, 'document.querySelector("[data-tab=\\\"1\\\"]").click()')
    drain(app, lambda: window.tabs.currentIndex() == 1)
    assert window.centralWidget() is window._legacy_shell and window.titlebar.isVisible()
    window.tabs.setCurrentIndex(0)
    assert window._glass_stack.currentWidget() is window._glass
    window.tabs.setCurrentIndex(4)
    drain(app, lambda: window.analytics is not None)
    assert not window.zoom.isEnabled() and not window.zoom.isVisible()
    assert window.zoom_message.isVisible() and window.ui_settings.zoom == 150
    window.tabs.setCurrentIndex(0)
    assert window.zoom.isEnabled() and window.ui_settings.zoom == 150


def test_stale_row_and_revoked_permission_cannot_edit(glass, app, monkeypatch):
    window, _, _ = glass
    _, ident, *_ = populate(app, glass)
    called = []
    monkeypatch.setattr(window, "edit_order", lambda: called.append(True))
    window._glass_command("edit", {"key": "order:999999"})
    assert not called
    original = window.can
    monkeypatch.setattr(window, "can", lambda p: p != Permission.ORDERS_EDIT and original(p))
    window._glass_command("edit", {"key": row_key(ident)})
    assert not called
    assert not window._glass.bridge.dispatch("__getattribute__", "{}")
    assert not window._glass.bridge.dispatch("edit", "[]")
    assert not window._glass.bridge.dispatch("edit", "x" * 5000)


def test_live_refresh_preserves_selected_order(glass, app):
    window, manager, admin = glass
    db, ident, line, master, department = populate(app, glass)
    window._glass_command("select", {"key": row_key(ident)})
    second = db.save_order(admin, date.today().strftime("%d-%m-%Y"), "Дневная",
                           master, department, [line], parent_id=ident)
    window._rc12_watch_tick()
    drain(app, lambda: window.orders_table.rowCount() == 2, timeout=10)
    assert window._selected_ref() == ident
    assert row_key(second) in {row["key"] for row in window.glass_state()["rows"]}


def test_snapshot_uses_models_without_another_sqlite_read(glass, app, monkeypatch):
    window, _, _ = glass
    populate(app, glass)
    def unexpected(*args, **kwargs):
        pytest.fail("Presentation snapshot attempted a database read")
    for method in ("list_orders", "get_employees", "get_departments", "order_history"):
        monkeypatch.setattr(window.db, method, unexpected)
    assert len(window.glass_state()["rows"]) == 1


def test_private_local_page_cannot_load_remote_or_other_local_files(glass):
    window, _, _ = glass
    class Request:
        def __init__(self, url): self.url = QUrl(url); self.blocked = None
        def requestUrl(self): return self.url
        def block(self, value): self.blocked = value
    for url, blocked in [("https://example.com/", True), ("file:///etc/passwd", True),
                         (QUrl.fromLocalFile(str(ASSET_ROOT / "orders.css")).toString(), False),
                         ("qrc:///qtwebchannel/qwebchannel.js", False)]:
        request = Request(url)
        window._glass.interceptor.interceptRequest(request)
        assert request.blocked is blocked


def test_responsive_window_keeps_caption_buttons_at_200_percent(glass, app):
    window, _, _ = glass
    window.resize(680, 620)
    window._glass_command("zoom", {"value": 200})
    drain(app, lambda: not window._rc18_zoom_timer.isActive())
    window._publish_glass_state(force=True)
    boxes = javascript(app, window, 'Array.from(document.querySelectorAll(".window-controls button")).map(b=>{const r=b.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}})')
    assert len(boxes) == 3
    assert all(b["x"] >= 0 and b["right"] <= window._glass.width() and b["bottom"] < 90 for b in boxes)
    assert javascript(app, window, 'getComputedStyle(document.getElementById("workspace-scroll")).overflowY') == "auto"


def test_workshop_switch_preserves_glass_class_and_single_session(glass, app):
    window, _, _ = glass
    session = window.session_tracker.id
    view = window._glass
    new_window = window._switch_to_workshop("smoking")
    assert new_window is window and isinstance(new_window, MainWindow)
    drain(app, lambda: new_window.workshop == "smoking" and not new_window._orders_running, timeout=12)
    assert new_window._glass is view
    assert new_window.session_tracker.id == session
    assert new_window.glass_state()["workshop"] == "Коптильный"

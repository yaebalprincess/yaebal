"""Visible controls, useful initial widths, and one first show of the editor."""
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import Qt, QEvent, QObject, QPoint
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QWidget, QDialog

from smartorder.config import SettingsStore, UiSettings
from smartorder import heavy_ui
from test_rc19_ui import app, ui, drain


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_caption_controls_visible_contrasting_and_functional(ui, app, theme):
    create, _, _, _ = ui
    SettingsStore().save(UiSettings(theme, 100))
    window = create()
    bar = window.titlebar
    assert len(bar.controls) == 3
    minimum, maximum, close = bar.controls
    assert all(b.isVisible() and b.width() >= 32 and b.height() >= 28 for b in bar.controls)
    assert close.geometry().right() == bar.width() - 1
    for button in bar.controls:
        picture = window.grab().toImage()
        origin = button.mapTo(window, QPoint(0, 0))
        x, y = button.width() // 2, button.height() // 2
        pixels = [picture.pixelColor(origin.x() + column, origin.y() + row).lightness()
                  for column in range(x - 8, x + 9) for row in range(y - 8, y + 9)]
        assert max(pixels) - min(pixels) > 80
    QTest.mouseClick(minimum, Qt.LeftButton)
    assert window.isMinimized()
    window.showNormal(); app.processEvents()
    QTest.mouseClick(maximum, Qt.LeftButton)
    assert window.isMaximized()
    drain(app, lambda: not window._window_motion.running)
    QTest.mouseClick(maximum, Qt.LeftButton)
    assert not window.isMaximized()
    window._rc4_exit_confirmed = True
    QTest.mouseClick(close, Qt.LeftButton)
    assert not window.isVisible()


@pytest.mark.parametrize("zoom", [100, 150, 200])
def test_order_columns_fit_headers_and_names_without_manual_resize(ui, app, zoom):
    create, _, _, _ = ui
    window = create()
    window._rc12_watch_timer.stop()
    drain(app, lambda: not window._orders_running)
    window.zoom.setValue(zoom)
    view = window.orders_table
    master = "1. Марина Константиновна Тлюстангелова"
    department = "1. Производство адыгейского сыра"
    view.report_model.set_rows([(1,"1","09-10-2026","Ночная",master,department,"09-10-2026 11:08:44",False)])
    drain(app, lambda: not view._width_timer.isActive())
    header = view.horizontalHeader(); font = QFontMetrics(header.font())
    for column, (_, label) in enumerate(view.report_model.columns):
        assert view.columnWidth(column) >= font.horizontalAdvance(label) + 40
    font = QFontMetrics(view.font())
    assert view.columnWidth(3) >= font.horizontalAdvance(master) + 16
    assert view.columnWidth(4) >= font.horizontalAdvance(department) + 16
    assert view.columnWidth(3) > view.columnWidth(5)
    assert not header.stretchLastSection()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_create_order_has_one_themed_first_show_without_secondary_windows(ui, app, monkeypatch, theme):
    create, _, _, _ = ui
    SettingsStore().save(UiSettings(theme, 100))
    window = create()
    shown = []
    class Shows(QObject):
        def eventFilter(self, obj, event):
            if isinstance(obj, QWidget) and obj.isWindow() and event.type() == QEvent.Show:
                shown.append(obj)
            return False
    events = Shows(); app.installEventFilter(events)
    captured = []
    def open_once(dialog):
        captured.append(dialog)
        assert not dialog.isVisible() and dialog.isMaximized()
        assert dialog.property("theme") == theme
        def no_second_maximize():pytest.fail("Editor maximized after the first show")
        monkeypatch.setattr(dialog, "showMaximized", no_second_maximize)
        assert dialog.order_date._popup.parent() is dialog
        assert not dialog.order_date._popup.isWindow()
        assert not dialog.order_date._popup.isVisible()
        dialog.show(); app.processEvents()
        assert dialog.isMaximized()
        picture = dialog.grab().toImage()
        value = picture.pixelColor(5, 5).lightness()
        assert value < 60 if theme == "dark" else value > 230
        dialog.reject()
        return QDialog.Rejected
    monkeypatch.setattr(heavy_ui.WorkOrderDialog, "exec_", open_once)
    try:
        QTest.mouseClick(window.create_order_btn, Qt.LeftButton)
        assert len(captured) == 1
        assert shown == captured
    finally:
        app.removeEventFilter(events)
        for dialog in captured:dialog.deleteLater()


def test_hidden_dialog_and_popup_never_create_native_handles(app, monkeypatch):
    dialog = QDialog()
    popup = QWidget(None, Qt.Popup)
    def forbidden_handle():pytest.fail("Hidden widget acquired a native handle")
    monkeypatch.setattr(dialog,"winId",forbidden_handle)
    monkeypatch.setattr(popup,"winId",forbidden_handle)
    with monkeypatch.context() as patch:
        patch.setattr(heavy_ui,"os",SimpleNamespace(name="nt"))
        for widget in (dialog, popup):
            heavy_ui._rc4_set_windows_titlebar_dark(widget, True)
            heavy_ui._rc14_force_windows_titlebar(widget, True)
    dialog.deleteLater(); popup.deleteLater()


def test_windows_hit_test_keeps_caption_controls_clickable_at_window_edges(ui, app, monkeypatch):
    import ctypes
    from ctypes import wintypes
    from smartorder import native_chrome
    create, _, _, _ = ui
    window=create()
    class Function:
        def __init__(self, callback):self.callback=callback
        def __call__(self,*args):return self.callback(*args)
    # Simulate a Windows client whose origin differs from the outer frame,
    # including negative screen coordinates on a monitor left of the primary.
    origin=(-900,120)
    def screen_to_client(hwnd, point):
        point._obj.x-=origin[0];point._obj.y-=origin[1]
        return 1
    user32=SimpleNamespace(ScreenToClient=Function(screen_to_client),IsZoomed=Function(lambda hwnd:0))
    def hit(point):
        msg=wintypes.MSG();msg.message=0x0084
        scale=window.devicePixelRatioF()
        x=origin[0]+round(point.x()*scale);y=origin[1]+round(point.y()*scale)
        msg.lParam=(x & 0xffff)|((y & 0xffff)<<16)
        return native_chrome.native_event(window,ctypes.addressof(msg))
    with monkeypatch.context() as patch:
        patch.setattr(native_chrome,"os",SimpleNamespace(name="nt"))
        patch.setattr(ctypes,"windll",SimpleNamespace(user32=user32),raising=False)
        for button in window.titlebar.controls:
            assert hit(button.mapTo(window,QPoint(button.width()-1,0)))==(True,1)
        assert hit(window.titlebar.title.mapTo(window,QPoint(30,20)))==(True,2)

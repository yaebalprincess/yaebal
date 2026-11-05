"""Regression coverage for profile preferences and the reported first-paint bugs."""
from datetime import datetime

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QWidget

from smartorder.appearance_config import normalize_appearance
from smartorder.config import SettingsStore, UiSettings, scheduled_theme
from smartorder.enterprise_ui import MainWindow, WorkshopDialog, CaptionButton
from smartorder.heavy_ui import FirstAdminDialog, LoginDialog, UserDialog, WorkOrderDialog
from smartorder.appearance import legacy_surface
from test_liquid_glass import app, system, drain


@pytest.fixture
def native(app, system):
    manager, admin = system
    window = MainWindow(manager._databases["packaging"], admin, manager)
    window.show(); app.processEvents()
    yield window
    if not sip.isdeleted(window):
        window._rc4_exit_confirmed = True; window.close(); window.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete); app.processEvents()


def test_profile_settings_are_separate_and_transient_settings_do_not_survive_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("SMARTORDER_NETWORK_ROOT", str(tmp_path / "share"))
    a, b = SettingsStore(1, "alice"), SettingsStore(2, "bob")
    settings = UiSettings(theme="dark", appearance=normalize_appearance(), auto_theme=True, about_theme=1)
    a.save(settings)
    assert SettingsStore(1, "alice").load() == settings
    assert b.load().theme == "light" and b.path != a.path
    settings.remember_personalization = False
    a.save(settings)
    assert not a.path.exists() and a.load().theme == "dark"
    assert SettingsStore(1, "alice").load().about_theme == 2
    settings.remember_personalization = True
    a.save(settings)
    assert SettingsStore(1, "alice").load().auto_theme


@pytest.mark.parametrize("hour,minute,theme", [(7,59,"dark"),(8,0,"light"),(16,59,"light"),(17,0,"dark")])
def test_schedule_boundaries(hour, minute, theme):
    assert scheduled_theme(datetime(2026,11,5,hour,minute)) == theme


def test_login_and_first_run_keep_native_frame_and_original_artwork(app, system, tmp_path, monkeypatch):
    from PIL import Image
    from smartorder import heavy_ui
    gif = tmp_path / "original.gif"
    Image.new("RGB", (12,12), "navy").save(gif, save_all=True,
        append_images=[Image.new("RGB", (12,12), "teal")], duration=100, loop=0)
    original = heavy_ui.resource_path
    monkeypatch.setattr(heavy_ui, "resource_path", lambda name: gif if str(name).endswith(".gif") else original(name))
    manager, _ = system
    for dialog in [LoginDialog(manager.auth), FirstAdminDialog(manager.auth)]:
        dialog.show(); app.processEvents()
        assert legacy_surface(dialog)
        assert not dialog.windowFlags() & Qt.FramelessWindowHint
        assert not dialog.testAttribute(Qt.WA_TranslucentBackground)
        assert getattr(dialog, "_liquid_backdrop", None) is None
        if isinstance(dialog, LoginDialog):
            assert dialog.bg.isVisible() and dialog.bg.movie is not None
            assert "background:rgba(255,255,255,220)" in dialog.username_edit.styleSheet()
            dialog.resize(520, 680); app.processEvents()
            assert dialog._form_container.size() == dialog.size()
        dialog.hide(); dialog.deleteLater()
    app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()


@pytest.mark.parametrize("role", ["Аналитик", "Бухгалтер", "Мастер Коптильный Цех"])
def test_personalization_available_to_every_role(app, system, role):
    manager, admin = system
    manager.auth.add_user(admin, role, "password123", role)
    user = manager.auth.authenticate(role, "password123")
    window = MainWindow(manager._databases["packaging"], user, manager)
    try:
        window.show(); window.tabs.setCurrentIndex(5); app.processEvents()
        assert window.tabs.tabText(4) == "Аналитика"
        assert window.tabs.tabText(5) == "Персонализация" and window.tabs.isTabEnabled(5)
        assert window.appearance_panel.isVisible()
        assert window.personalization_session_label.text().startswith("Текущая сессия:")
    finally:
        window._rc4_exit_confirmed = True; window.close(); window.deleteLater()
        app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()


def test_first_tab_visits_do_not_show_detached_windows_and_admin_has_no_personalization(native, app):
    already_visible = {id(w) for w in QApplication.topLevelWidgets() if w.isVisible()}
    for index in (1,2,3,4,5,6,0):
        host = native.tabs.widget(index)
        native.tabs.setCurrentIndex(index); app.processEvents()
        assert native.tabs.widget(index) is host
        assert host.isVisible() and not host.isWindow()
        assert all(not w.isVisible() or id(w) in already_visible for w in QApplication.topLevelWidgets())
    native.tabs.setCurrentIndex(3)
    assert not native.tabs.currentWidget().findChild(QWidget, "AppearancePanel")


def test_personalization_theme_about_examples_and_closed_font_wheel(native, app, monkeypatch):
    native.tabs.setCurrentIndex(5); app.processEvents()
    panel = native.appearance_panel
    family, _, _, _, sample = panel.font_controls["body"]
    before = family.currentIndex()
    wheel = QWheelEvent(QPointF(10,10), QPointF(family.mapToGlobal(QPoint(10,10))),
        QPoint(), QPoint(0,120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    app.sendEvent(family, wheel)
    assert family.currentIndex() == before
    assert "Создание наряда" in sample.text()
    panel.theme_toggle.setChecked(True); app.processEvents()
    assert native.theme.isChecked() and native.ui_settings.theme == "dark"
    assert panel.theme_label.text() == "Тёмная тема"
    hidden = QPushButton("Отложенный элемент", native.tabs.widget(5))
    hidden.hide(); hidden.setProperty("theme", "light")
    hidden.show(); app.processEvents()
    assert hidden.property("theme") == "dark"
    hidden.hide(); hidden.deleteLater()
    monkeypatch.setattr("smartorder.config.scheduled_theme", lambda now=None: "light")
    panel.auto_theme.setChecked(True)
    assert native.ui_settings.auto_theme and not native.theme.isChecked()
    native.theme.setChecked(True)
    assert not native.ui_settings.auto_theme and not panel.auto_theme.isChecked()
    native.tabs.setCurrentIndex(6)
    native.tabs.setCurrentIndex(5)
    panel.about_theme.setCurrentIndex(0); panel.save()
    native.tabs.setCurrentIndex(6); app.processEvents()
    assert any(legacy_surface(w) for w in native.tabs.widget(6).findChildren(QWidget))
    native.tabs.setCurrentIndex(5); panel.about_theme.setCurrentIndex(1); panel.save()
    native.tabs.setCurrentIndex(6); app.processEvents()
    assert native.tabs.widget(6).findChild(QLabel,"TitleLabel").text() == "Smart Order"


def test_user_dialog_order_caption_symbols_and_visible_backup(native, app):
    dialog = UserDialog(parent=native)
    dialog.show(); app.processEvents()
    assert dialog.windowTitle() == "Создание нового пользователя"
    label = dialog.findChild(QLabel,"UserDialogSubtitle")
    assert label.text() == "Заполните данные для нового пользователя" and not label.font().bold()
    dialog.hide(); dialog.deleteLater()
    editor = WorkOrderDialog(native.db, native.user, parent=native)
    editor.show(); app.processEvents()
    assert isinstance(editor._glass_chrome.controls[0], CaptionButton)
    assert [b.kind for b in editor._glass_chrome.controls] == ["min","max","close"]
    assert editor._glass_grip is not None
    editor.hide(); editor.deleteLater()
    native.tabs.setCurrentIndex(3); app.processEvents()
    for label in native._admin_filter_labels:
        assert "#3A3A3C" not in label.styleSheet()
    backup_buttons = [b for b in native.tabs.widget(3).findChildren(QPushButton) if b.text() == "Создать бэкап"]
    assert backup_buttons and not backup_buttons[0].icon().isNull()
    shops = WorkshopDialog(native)
    assert all(not b.icon().isNull() for b in shops.buttons.buttons())
    shops.deleteLater()
    box = QMessageBox(QMessageBox.Information,"Резервная копия","Учётные записи и сессии сохранены",QMessageBox.Ok,native)
    box.show(); app.processEvents()
    assert box._glass_chrome.isVisible() and not box.testAttribute(Qt.WA_TranslucentBackground)
    assert box.grab().toImage().pixelColor(box.width()//2,box.height()//2).alpha() == 255
    box.hide(); box.deleteLater()
    app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()

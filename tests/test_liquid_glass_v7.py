"""Account permissions, portable profiles and interaction regressions through Qt/Chromium."""
from datetime import datetime,timedelta
import json
from pathlib import Path
import threading
import time
import pytest
from PyQt5 import sip
from PyQt5.QtCore import Qt,QEvent,QPoint,QDateTime
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication,QPushButton,QDialogButtonBox,QFileDialog
from smartorder.account_ui import AccountDialog
from smartorder.config import UiSettings,SettingsStore
from smartorder.glass_ui import MainWindow
from smartorder.heavy_ui import WorkOrderDialog
from smartorder.i18n import LANGUAGES,CATALOG,TRANSLATIONS,source_text,tr
from smartorder.profile_sync import export_current_config,portable_config,read_config,load_shared_settings,pending_path
from smartorder.security import Permission,ROLES
from test_liquid_glass import app,system,glass,javascript,drain


@pytest.fixture
def economist(app,system):
    manager,admin=system
    manager.auth.add_user(admin,"economist","password123","Экономист")
    user=manager.auth.authenticate("economist","password123")
    window=MainWindow(manager._databases["packaging"],user,manager);window.resize(1727,910);window.show()
    drain(app,lambda:window._glass_ready and not window._orders_running,timeout=12)
    try:yield window,manager,user
    finally:
        if not sip.isdeleted(window):window._rc4_exit_confirmed=True;window.close();window.deleteLater()
        app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()


def test_theme_clickable_at_both_edges_without_stylesheet_replacement(glass,app,monkeypatch):
    window,_,_=glass
    for index in (1,2,3,4,5,6,0):window.tabs.setCurrentIndex(index);app.processEvents()
    calls=[];original=app.setStyleSheet
    monkeypatch.setattr(app,"setStyleSheet",lambda css:(calls.append(css),original(css))[-1])
    times=[]
    for point,expected in ((QPoint(44,13),"dark"),(QPoint(2,13),"light")):
        started=time.perf_counter();QTest.mouseClick(window.theme,Qt.LeftButton,pos=point)
        assert window.ui_settings.theme==expected
        drain(app,lambda:not window._theme_apply_timer.isActive())
        times.append(time.perf_counter()-started)
        assert app._liquid_theme==expected
    assert not calls
    assert getattr(window.centralWidget(), "_liquid_transition", None) is None
    assert all('[theme="'+theme+'"]' in app.styleSheet() for theme in ("light","dark"))
    print("Theme with all tabs loaded, seconds:",times)


def test_tab_labels_fit_after_fractional_zoom_and_language_change(glass,app):
    window,_,_=glass
    for code in ("ru","de","fr","ja","tt","kk"):
        window.set_language(code);window.zoom.setValue(111);window._rc18_commit_zoom();app.processEvents()
        bar=window.tabs.tabBar()
        for index in range(bar.count()):
            assert bar.tabRect(index).width()>=bar.fontMetrics().horizontalAdvance(bar.tabText(index))+2*int(bar.property("tabHorizontalPadding"))+8


def test_economist_restricted_region_notifications_and_workshop_anchor(economist,app):
    window,_,user=economist
    assert "Аналитик" not in ROLES and user.can(Permission.NOTIFICATIONS_VIEW)
    assert not window.tabs.isTabEnabled(1) and not window.tabs.isTabEnabled(2)
    window._publish_glass_state(force=True)
    assert javascript(app,window,'document.getElementById("access-overlay").hidden') is False
    assert javascript(app,window,'document.getElementById("access-overlay").parentElement.classList.contains("orders-top")') is True
    assert javascript(app,window,'getComputedStyle(document.getElementById("access-overlay")).cursor')=="not-allowed"
    assert javascript(app,window,'document.getElementById("empty-orders").hidden') is False
    assert javascript(app,window,'document.getElementById("date").disabled') is True
    assert window.titlebar.bell.isVisible() and window.titlebar.bell.isEnabled()
    window.show_notifications();app.processEvents();assert window.notification_popup.isVisible();window.notification_popup.close()
    window.choose_workshop();app.processEvents();popup=window.workshop_menu
    expected=window.titlebar.badge.mapToGlobal(QPoint(0,window.titlebar.badge.height()))
    assert 0<=popup.y()-expected.y()<=6
    assert all(action.isEnabled() for action in popup.actions());popup.close()


def test_first_channel_frame_receives_permissions_without_manual_push(economist,app):
    window,_,_=economist
    drain(app,lambda:javascript(app,window,'document.getElementById("access-overlay").hidden') is False)
    drain(app,lambda:window._glass_painted)
    assert javascript(app,window,'document.getElementById("create").disabled') is True
    assert javascript(app,window,'document.getElementById("empty-message").textContent')=="Наряды пока не созданы."


def test_pointer_and_popup_styles_use_app_palette(glass,app):
    window,_,_=glass;window.tabs.setCurrentIndex(3);app.processEvents()
    for combo in (window.order_filter_master,window.audit_user_filter):
        combo.showPopup();app.processEvents();frame=combo.view().window()
        assert frame.isVisible() and frame.windowFlags()&Qt.NoDropShadowWindowHint
        assert frame.property("plainSurface") and "outline:0" in combo.view().styleSheet()
        assert "#000000" not in combo.view().styleSheet();combo.hidePopup()
    assert javascript(app,window,'getComputedStyle(document.getElementById("master-trigger")).outlineStyle')=="none"


def test_order_footer_buttons_share_bottom_baseline(glass,app):
    window,_,_=glass;dialog=WorkOrderDialog(window.db,window.user,parent=window);dialog.resize(1900,980);dialog.show();app.processEvents()
    try:
        assert dialog._aligned_footer
        names={"Добавить работников","Добавить работы","Удалить выбранных","Сохранить","Отмена","Выгрузить в Excel","Выгрузить в EXCEL"}
        buttons=[b for b in dialog._action_footer.findChildren(QPushButton) if b.text() in names]
        assert len(buttons)>=6
        bottoms=[b.mapTo(dialog,QPoint(0,b.height())).y() for b in buttons]
        assert max(bottoms)-min(bottoms)<=2
        assert dialog.height()-max(bottoms)<55
    finally:dialog.hide();dialog.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete)


def test_account_editor_persists_custom_grants_and_future_activation(glass,app):
    window,manager,admin=glass
    dialog=AccountDialog("future","Экономист",parent=window);dialog.show();app.processEvents()
    try:
        assert "Аналитик" not in [dialog.role_list.item(i).data(Qt.UserRole) for i in range(dialog.role_list.count())]
        dialog.password.setText("password123");dialog.custom.setChecked(True)
        dialog.permission_checks[Permission.EMPLOYEES_CREATE].setChecked(True)
        assert dialog.permission_checks[Permission.EMPLOYEES_VIEW].isChecked()
        dialog.schedule.setChecked(True);dialog.activation.setDateTime(QDateTime.currentDateTime().addDays(2));assert dialog.ok.isEnabled()
        options=dialog.account_options();manager.auth.add_user(admin,dialog.username.text(),dialog.password.text(),dialog.selected_roles(),**options)
        row=next(r for r in manager.auth.list_users() if r[1]=="future");saved=manager.auth.user_options(row[0])
        assert Permission.EMPLOYEES_CREATE in saved["permissions"] and saved["activate_at"] and not row[3]
        assert manager.auth.authenticate("future","password123") is None
    finally:dialog.hide();dialog.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete)


@pytest.mark.parametrize("code",["kk","fr","de","ja","tt"])
def test_new_language_catalog_is_complete_and_values_stay_canonical(glass,app,code):
    window,_,_=glass;window.tabs.setCurrentIndex(5);app.processEvents()
    assert all(key in TRANSLATIONS[code] for key in CATALOG)
    panel=window.appearance_panel;assert panel.language.count()==8
    panel.language.setCurrentIndex(panel.language.findData(code));app.processEvents()
    assert window.tabs.tabText(5)==TRANSLATIONS[code]["Персонализация"]
    assert source_text(window.order_filter_shift)=="Все смены"
    window.tabs.setCurrentIndex(0);window._publish_glass_state(force=True)
    drain(app,lambda:javascript(app,window,'document.documentElement.lang')==code)
    assert javascript(app,window,'document.querySelector("#empty-orders img").complete') is True


def test_export_is_one_dated_file_and_shared_profile_loads_on_second_pc(glass,app,monkeypatch,tmp_path):
    window,manager,user=glass;settings=UiSettings(theme="dark",zoom=111,language="kk",sync_personalization=True)
    first=export_current_config(user,settings);settings.language="ja";second=export_current_config(user,settings)
    assert list(second.parent.glob("*.json"))==[second] and datetime.now().strftime("%Y-%m-%d") in second.name
    assert read_config(json.loads(second.read_text())).language=="ja"
    manager.auth.save_personalization(user,True,portable_config(settings))
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"second-pc"))
    loaded,error=load_shared_settings(manager.auth,user,UiSettings())
    assert not error and loaded.language=="ja" and loaded.zoom==111 and loaded.theme=="dark" and loaded.sync_personalization


def test_background_sync_keeps_theme_responsive_and_sends_latest_config(glass,app,monkeypatch):
    window,manager,user=glass;window.tabs.setCurrentIndex(5);app.processEvents()
    entered=threading.Event();release=threading.Event();original=manager.auth.save_personalization
    def delayed(*args,**kwargs):
        entered.set();release.wait(3);return original(*args,**kwargs)
    monkeypatch.setattr(manager.auth,"save_personalization",delayed)
    try:
        window.appearance_panel.sync_config.setChecked(True);drain(app,entered.is_set)
        QTest.mouseClick(window.appearance_panel.theme_toggle,Qt.LeftButton,pos=QPoint(44,13))
        assert window.ui_settings.theme=="dark";drain(app,lambda:not window._theme_apply_timer.isActive())
        release.set()
        drain(app,lambda:not window.profile_sync.running and window.profile_sync.pending is None,timeout=8)
        assert manager.auth.get_personalization(user)["payload"]["settings"]["theme"]=="dark"
        assert not pending_path(user).exists()
    finally:release.set()


def test_shared_files_cannot_read_local_files_outside_managed_wallpapers(glass,tmp_path):
    window,_,_=glass;secret=tmp_path/"secret.txt";secret.write_text("private data")
    settings=UiSettings(appearance={"background_mode":"custom","background_file":str(secret)})
    payload=portable_config(settings)
    assert "wallpaper" not in payload and payload["settings"]["appearance"]["background_file"]==""
    payload["settings"]["appearance"].update(background_mode="custom",background_file=str(secret))
    loaded=read_config(payload);assert loaded.appearance["background_mode"]=="none"


def test_fullscreen_and_windowed_modes_restore_geometry(glass,app):
    from smartorder.heavy_ui import _RC4FullscreenIcon

    window,_,_=glass;before=window.geometry()
    window.toggle_window_mode(True)
    drain(app,lambda:window.isFullScreen() and not window._window_motion.running)
    assert window.size() == window.screen().geometry().size()
    assert window.centralWidget().size() == window.size()
    feedback = window._fullscreen_feedback
    assert feedback.isVisible() and not feedback.isWindow()
    assert feedback.geometry().center() == window.rect().center()
    assert feedback.findChild(_RC4FullscreenIcon).entering
    window.toggle_window_mode(True)
    drain(app,lambda:not window.isFullScreen() and not window._window_motion.running)
    assert window.geometry()==before
    feedback = window._fullscreen_feedback
    assert feedback.isVisible() and not feedback.findChild(_RC4FullscreenIcon).entering
    assert feedback.geometry().center() == window.rect().center()
    drain(app,lambda:window._fullscreen_feedback is None,timeout=3)


def test_loading_a_shared_file_keeps_recipient_sync_choice(glass,app,monkeypatch):
    window,_,user=glass;window.tabs.setCurrentIndex(5);app.processEvents()
    file=export_current_config(user,UiSettings(theme="dark",language="de",zoom=111,sync_personalization=True))
    monkeypatch.setattr(QFileDialog,"getOpenFileName",lambda *_:(str(file),""))
    loaded=window.import_personalization();app.processEvents()
    assert loaded.language=="de" and window.tabs.tabText(5)=="Personalisierung"
    assert window.zoom.value()==111 and not window.ui_settings.sync_personalization
    assert not window.appearance_panel.sync_config.isChecked()


def test_custom_tab_access_and_disabled_actions_use_grants(economist,app):
    window,manager,user=economist
    admin=manager.auth.authenticate("admin","password123")
    grants=[Permission.CATALOG_VIEW,Permission.CATALOG_CREATE,Permission.EMPLOYEES_VIEW,
        Permission.ADMIN_VIEW,Permission.USERS_VIEW,Permission.ANALYTICS_VIEW]
    manager.auth.update_user(admin,user.id,user.username,user.role,permissions=grants)
    window._read_account_access();drain(app,lambda:window.user.permissions==set(grants))
    assert window.tabs.isTabEnabled(1) and window.tabs.isTabEnabled(2) and window.tabs.isTabEnabled(3)
    assert not window.tabs.isTabEnabled(0)
    window.tabs.setCurrentIndex(1);app.processEvents()
    add=next(b for b in window.tabs.currentWidget().findChildren(QPushButton) if b.property("alignedAction")=="add")
    imp=next(b for b in window.tabs.currentWidget().findChildren(QPushButton) if b.property("alignedAction")=="import")
    assert add.isEnabled() and not imp.isEnabled()
    window.tabs.setCurrentIndex(3);app.processEvents();drain(app,lambda:window.users_table.rowCount()>0)
    add_user=next(b for b in window.tabs.currentWidget().findChildren(QPushButton) if b.text()=="Добавить пользователя")
    assert not add_user.isEnabled() and not window.access_control_check.isEnabled()
    for row in range(window.users_table.rowCount()):
        assert all(not b.isEnabled() for b in window.users_table.cellWidget(row,3).findChildren(QPushButton))
    window.tabs.setCurrentIndex(4);drain(app,lambda:window.analytics.report is not None)
    assert not window.analytics.export.isEnabled()


def test_revoked_view_clears_display_and_selects_personalization(economist,app):
    window,manager,user=economist;admin=manager.auth.authenticate("admin","password123")
    manager.auth.update_user(admin,user.id,user.username,user.role,permissions=[])
    window._read_account_access();drain(app,lambda:not window.user.permissions)
    assert window.tabs.currentIndex()==5 and window.appearance_panel.isVisible()
    assert not window.titlebar.bell.isVisible()
    assert all(not window.tabs.isTabEnabled(i) for i in range(5))
    assert not window.glass_state()["rows"]

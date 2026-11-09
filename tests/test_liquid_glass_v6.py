"""Exercise the requested v6 changes through the actual Qt and Chromium UI."""
from datetime import datetime
import json
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, QPoint, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QWidget
from smartorder.config import SettingsStore, UiSettings
from smartorder.appearance_config import normalize_appearance
from smartorder.heavy_ui import AnimatedToggle, UserDialog
from smartorder.i18n import source_text, set_language
from smartorder.workspace_ui import WORKSHOP_PHOTOS, WorkshopLoadingDialog, workshop_photo_path, workshop_picture
from test_liquid_glass import app, system, glass, javascript, drain


def test_startup_flag_preserves_saved_preferences(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path));monkeypatch.setenv("SMARTORDER_NETWORK_ROOT",str(tmp_path/"share"))
    store=SettingsStore(1,"alice");settings=UiSettings(theme="dark",zoom=130,language="es")
    store.save(settings);store.set_startup_enabled(settings,False)
    assert json.loads(store.path.read_text())["language"]=="es"
    fresh=SettingsStore(1,"alice");defaults=fresh.load()
    assert defaults.zoom==100 and defaults.language=="ru" and not defaults.remember_personalization
    fresh.save(defaults)
    assert json.loads(store.path.read_text())["zoom"]==130
    fresh.set_startup_enabled(defaults,True)
    assert SettingsStore(1,"alice").load().language=="es"


def test_zoom_is_local_and_not_applied_while_dragging(glass,app,monkeypatch):
    window,_,_=glass
    window.tabs.setCurrentIndex(1);app.processEvents()
    baseline=app.styleSheet();calls=[]
    original=app.setStyleSheet
    monkeypatch.setattr(app,"setStyleSheet",lambda value:(calls.append(value),original(value))[-1])
    window.zoom.setSliderDown(True)
    for value in (110,120,130,140):window.zoom.setValue(value)
    assert not window._rc18_zoom_timer.isActive()
    window.zoom.setSliderDown(False);window._rc18_commit_zoom();app.processEvents()
    assert not calls and app.styleSheet()==baseline
    assert window.ui_settings.zoom==140
    add=next(b for b in window.tabs.currentWidget().findChildren(QPushButton) if b.property("alignedAction")=="add")
    assert add.font().pixelSize()==round(normalize_appearance(window.ui_settings.appearance)["fonts"]["buttons"]["size"]*1.4)
    window.tabs.setCurrentIndex(4);app.processEvents()
    assert window.zoom_message.isVisible() and not window.zoom.isVisible()
    assert window.zoom_message.text()=="В данной вкладке функция масштаба недоступна"
    assert window.tabs.currentWidget()._page_scale_key[0]==100
    window._apply_zoom(180)
    assert window.ui_settings.zoom==140
    window.tabs.setCurrentIndex(0)
    assert window.zoom.isVisible() and window.zoom.value()==140


def test_tabs_no_new_windows_and_reference_actions_align(glass,app):
    window,_,_=glass
    known={id(w) for w in app.topLevelWidgets() if w.isVisible()}
    shown = []

    class WindowShows(QObject):
        def eventFilter(self, obj, event):
            if (event.type() == QEvent.Show and isinstance(obj, QWidget)
                    and obj.isWindow() and id(obj) not in known):
                shown.append((obj.metaObject().className(), obj.objectName()))
            return False

    observer = WindowShows()
    app.installEventFilter(observer)
    positions=[]
    try:
        for index in (1,2,3,4,5,6,1,2,0):
            window.tabs.setCurrentIndex(index);app.processEvents()
            if index in (1,2):
                buttons={b.property("alignedAction"):b for b in window.tabs.currentWidget().findChildren(QPushButton) if b.property("alignedAction")}
                positions.append(tuple((kind,buttons[kind].mapTo(window,QPoint()),buttons[kind].size()) for kind in ("add","import")))
    finally:
        app.removeEventFilter(observer)
    assert not shown
    assert all(p==positions[0] for p in positions)


def test_empty_states_and_about_bottom(glass,app):
    window,_,_=glass
    assert javascript(app,window,'document.getElementById("empty-orders").hidden') is False
    assert "создайте наряд" in javascript(app,window,'document.getElementById("empty-orders").textContent')
    for width, height in ((1727, 910), (900, 560), (640, 440)):
        window.resize(width, height)
        app.processEvents()
        horizontal, vertical = javascript(app, window, '''(() => {
            const bounds = selector => document.querySelector(selector).getBoundingClientRect();
            const panel = bounds('#table-panel');
            const header = bounds('#orders-table thead');
            const icon = bounds('#empty-orders img');
            const label = bounds('#empty-message');
            return [Math.abs(icon.left + icon.right - panel.left - panel.right) / 2,
                    Math.abs(icon.top + label.bottom - header.bottom - panel.bottom) / 2];
        })()''')
        assert horizontal < 2 and vertical < 2
    window.resize(1727, 910)
    for index,name in [(1,"work_empty"),(2,"people_empty")]:
        window.tabs.setCurrentIndex(index);app.processEvents()
        empty=getattr(window,name)
        assert empty.isVisible() and empty.geometry().center()==empty.parentWidget().rect().center()
    window.tabs.setCurrentIndex(6);app.processEvents()
    host=window.tabs.currentWidget();label=window.about_session_label
    bottom=label.mapTo(host,QPoint(0,label.height())).y()
    assert host.height()-bottom<45


def test_languages_preserve_domain_data_and_hide_header_toggle(glass,app):
    window,_,_=glass
    window.tabs.setCurrentIndex(5);app.processEvents()
    assert window.theme.isHidden() and window.theme_caption.isHidden()
    panel=window.appearance_panel
    assert panel.remember.text()=="Применять сохраненные настройки персонализации при запуске"
    for code,title in [("en","Personalization"),("es","Personalización"),("ru","Персонализация")]:
        panel.language.setCurrentIndex(panel.language.findData(code));app.processEvents()
        assert window.tabs.tabText(5)==title
        window.tabs.setCurrentIndex(0);window._publish_glass_state(force=True)
        drain(app,lambda:javascript(app,window,'document.documentElement.lang')==code)
        assert source_text(window.order_filter_shift)=="Все смены"
        window.tabs.setCurrentIndex(5)
    panel.theme_toggle.setChecked(True);drain(app,lambda:panel.theme_toggle._offset==32)
    assert window.theme.isChecked() and window.ui_settings.theme=="dark"
    panel.theme_toggle.setChecked(False);drain(app,lambda:panel.theme_toggle._offset==2)
    assert not window.theme.isChecked() and window.ui_settings.theme=="light"


def test_resizable_columns_round_trip_to_profile(glass,app):
    window,_,_=glass
    before=javascript(app,window,'document.querySelector("#orders-table th").getBoundingClientRect().width')
    javascript(app,window,'document.querySelector(".column-resizer").dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowRight",bubbles:true}));')
    drain(app,lambda:len(window.ui_settings.order_columns)==6)
    after=javascript(app,window,'document.querySelector("#orders-table th").getBoundingClientRect().width')
    assert after>before+8
    assert SettingsStore(window.user.id,window.user.username).load().order_columns==window.ui_settings.order_columns
    old=window.ui_settings.order_columns[:]
    window._glass_command("columns",{"widths":[True]*6})
    assert window.ui_settings.order_columns==old


def test_user_title_checkboxes_and_password_message(glass,app):
    window,manager,admin=glass
    dialog=UserDialog(parent=window);dialog.show();app.processEvents()
    try:
        assert len([w for w in dialog.findChildren(QLabel) if w.text()=="Создание нового пользователя"])==1
        assert dialog.findChild(QLabel,"UserDialogSubtitle").font().bold() is False
        dialog.role_list.item(0).setCheckState(Qt.Checked);app.processEvents()
        assert "Администратор" in dialog.selected_roles()
        image=dialog.role_list.viewport().grab().toImage()
        rect=dialog.role_list.visualItemRect(dialog.role_list.item(0))
        blacks=sum(image.pixelColor(x,y)==QColor("black") for x in range(0,min(29,image.width())) for y in range(max(0,rect.top()),min(image.height(),rect.bottom())))
        assert blacks<5
    finally:dialog.hide();dialog.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete)
    with pytest.raises(ValueError,match="не менее 8 символов"):
        manager.auth.add_user(admin,"new-user","short","Аналитик")


def test_workshop_switch_reuses_web_view_and_keeps_session(glass,app):
    window,_,_=glass;view=window._glass;tracker=window.session_tracker
    assert window._switch_to_workshop("smoking") is window
    loading = window._workshop_loading
    assert loading.workshop == "smoking"
    drain(app,lambda:window.workshop=="smoking" and not window._orders_running,timeout=10)
    assert window._glass is view and window.session_tracker is tracker and window.isVisible()
    drain(app, lambda: hasattr(loading, "_fade_out"))
    assert loading._fade_out.duration() > 0
    drain(app, lambda: sip.isdeleted(loading) or not loading.isVisible())


@pytest.mark.parametrize("key",["packaging","smoking","drying","rennet","adyghe"])
def test_loading_uses_workshop_specific_file(app,tmp_path,monkeypatch,key):
    monkeypatch.setenv("SMARTORDER_NETWORK_ROOT",str(tmp_path));folder=tmp_path/"resources";folder.mkdir()
    image=QImage(40,30,QImage.Format_RGB32);image.fill(QColor("#657d99"));assert image.save(str(folder/WORKSHOP_PHOTOS[key]))
    workshop_picture.cache_clear()
    assert workshop_photo_path(key)==folder/WORKSHOP_PHOTOS[key]
    dialog=WorkshopLoadingDialog(key);dialog.show();app.processEvents()
    assert not dialog.picture.isNull() and getattr(dialog,"_liquid_backdrop",None) is None
    dialog.hide();dialog.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete)

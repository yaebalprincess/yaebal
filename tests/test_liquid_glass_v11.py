"""Click-driven lessons, shared calendar and first-frame/child-popup regressions."""
from types import SimpleNamespace

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QDate, QEvent, QPoint, QRect, QSize, Qt, QTimer
from PyQt5.QtGui import QPalette
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QPushButton, QTextBrowser

from smartorder import heavy_ui
from smartorder.config import SettingsStore, UiSettings, local_drafts_dir
from smartorder.glass_ui import MainWindow
from test_liquid_glass import app, drain, glass, javascript, populate, system


def script(app,view,expression):
    result=[];view.page().runJavaScript(expression,result.append)
    drain(app,lambda:bool(result),timeout=10)
    return result[0]


def close(window,app):
    window._rc4_exit_confirmed=True;window.close();window.deleteLater()
    app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()


@pytest.mark.parametrize("editing",[False,True])
def test_editor_has_no_export_actions_and_uses_main_calendar(glass,app,editing):
    owner,manager,user=glass;db,identity,*_=populate(app,glass)
    dialog=heavy_ui.HeavyWorkOrderDialog(db,user,db.get_order(identity) if editing else None,parent=owner)
    dialog.show()
    try:
        assert not any(button.text().startswith("Выгрузить") or button.text()=="Прямая печать" for button in dialog.findChildren(QPushButton))
        field=dialog.order_date;popup=field._popup
        assert not popup.isWindow() and popup.parentWidget() is dialog
        QTest.mouseClick(field,Qt.LeftButton,pos=field._icon_rect().center())
        drain(app,lambda:popup.isVisible() and popup.ready and not popup.cover.isVisible(),timeout=12)
        assert script(app,popup.view,'document.querySelectorAll("[data-cal-date]").length')==42
        assert script(app,popup.view,'getComputedStyle(document.querySelector(".calendar-heading")).display')=="grid"
        if not editing:
            owner.set_language("en");popup.publish()
            drain(app,lambda:script(app,popup.view,'document.querySelector(".calendar-weekdays span").textContent')=="Mon")
            assert script(app,popup.view,'document.querySelector("[data-cal=today]").textContent')=="Today"
        chosen=field.date().addDays(1)
        script(app,popup.view,'document.querySelector("[data-cal-date=\\\"'+chosen.toString(Qt.ISODate)+'\\\"]").click();document.querySelector("[data-cal=apply]").click()')
        drain(app,lambda:field.date()==chosen and not popup.isVisible())
    finally:
        dialog._save_draft=lambda:None;dialog.reject();dialog.deleteLater();app.processEvents()


@pytest.mark.parametrize("theme",["light","dark"])
def test_book_opens_opaque_start_and_f1_readable_help(glass,app,theme):
    owner,_,_=glass
    owner.theme.setChecked(theme=="dark")
    drain(app,lambda:owner.ui_settings.theme==theme)
    QTest.mouseClick(owner.titlebar.help,Qt.LeftButton)
    start=owner._training_start
    assert start.isVisible() and start.windowTitle()=="Обучение: как работать с нарядами?"
    assert not start.testAttribute(Qt.WA_TranslucentBackground)
    assert start.palette().color(QPalette.Window).alpha()==255
    assert any(button.text()=="Начать!" for button in start.findChildren(QPushButton))
    assert owner.titlebar.help.size()==owner.titlebar.bell.size()
    assert owner.titlebar.bell.text()=="" and not owner.titlebar.bell.icon().isNull()
    start.reject()
    from smartorder.context_help import show_context_help
    show_context_help(owner)
    help=owner._section_help;browser=help.findChild(QTextBrowser)
    assert browser.toPlainText() and not help.testAttribute(Qt.WA_TranslucentBackground)
    lightness=browser.palette().color(QPalette.Text).lightness()
    assert lightness>190 if theme=="dark" else lightness<100
    help.reject()


def test_workshop_popup_stays_inside_main_window(glass,app):
    owner,_,_=glass
    top={id(widget) for widget in QApplication.topLevelWidgets() if widget.isVisible()}
    owner.choose_workshop();app.processEvents();popup=owner.workshop_menu
    assert popup.isVisible() and not popup.isWindow() and popup.parentWidget() is owner
    assert {id(widget) for widget in QApplication.topLevelWidgets() if widget.isVisible()}==top
    assert owner.rect().contains(popup.geometry())
    QTest.mouseClick(owner.titlebar.title,Qt.LeftButton)
    assert not popup.isVisible() and owner.isVisible()


def test_empty_state_and_bell_are_drawn_as_vectors(glass,app):
    owner,_,_=glass;owner.tabs.setCurrentIndex(2)
    drain(app,lambda:hasattr(owner,"people_empty") and owner.people_empty.isVisible())
    empty=owner.people_empty;empty.grab()
    assert empty._vector_icon.isValid() and "<img" not in empty.text()
    from smartorder.symbols import symbol_icon
    for size in (20,40,80):
        picture=symbol_icon("bell").pixmap(QSize(size,size)).toImage()
        alpha={picture.pixelColor(x,y).alpha() for x in range(picture.width()) for y in range(picture.height())}
        assert len(alpha)>10


def test_first_frame_cover_and_loading_wait_for_browser(system,app):
    manager,user=system
    SettingsStore(user.id,user.username).save(UiSettings(theme="dark"))
    owner=MainWindow(manager.database("packaging",user),user,manager)
    from smartorder.workspace_ui import WorkshopLoadingDialog,reveal_after_first_frame
    loading=WorkshopLoadingDialog("packaging");loading.show();owner.show()
    try:
        assert owner._startup_cover.isVisible() and not owner._glass_painted
        assert owner._startup_cover.grab().toImage().pixelColor(5,5).lightness()<70
        called=[];reveal_after_first_frame(owner,loading,lambda:called.append(True))
        drain(app,lambda:owner._glass_painted and getattr(owner,"_startup_revealed",False),timeout=12)
        assert not owner._startup_cover.isVisible()
        drain(app,lambda:called and (sip.isdeleted(loading) or not loading.isVisible()))
    finally:close(owner,app)


@pytest.mark.parametrize("available,rect",[(QRect(0,0,1920,1040),QRect(100,1060,1200,800)),
    (QRect(-1920,0,1920,1040),QRect(-1800,1200,1000,600)),(QRect(0,40,1920,1000),QRect(-4000,-900,1200,800))])
def test_drag_keeps_caption_reachable(available,rect):
    from smartorder.native_chrome import visible_title_geometry
    fixed=visible_title_geometry(rect,available)
    assert fixed.size()==rect.size()
    assert available.top()<=fixed.top()<=available.bottom()-47
    assert fixed.right()>=available.left()+95 and fixed.left()<=available.right()-95


def test_frame_is_not_recreated_when_focus_moves_to_menu(glass,app,monkeypatch):
    import ctypes
    from smartorder import native_chrome
    owner,_,_=glass;calls=[]
    fake=SimpleNamespace(user32=SimpleNamespace(SetWindowPos=lambda *args:calls.append(args)),
        dwmapi=SimpleNamespace(DwmExtendFrameIntoClientArea=lambda *args:0,DwmSetWindowAttribute=lambda *args:0))
    monkeypatch.setattr(native_chrome,"os",SimpleNamespace(name="nt"))
    monkeypatch.setattr(ctypes,"windll",fake,raising=False)
    native_chrome.apply_frame(owner,False);native_chrome.apply_frame(owner,False)
    assert len(calls)==1
    native_chrome.apply_frame(owner,True)
    assert len(calls)==2


def click_lesson(app,tour):
    drain(app,lambda:not tour.target.isEmpty())
    point=tour.target.center();widget=QApplication.widgetAt(point)
    assert widget is not None and widget is not tour.coach
    QTest.mouseClick(widget,Qt.LeftButton,pos=widget.mapFromGlobal(point))


def choose_combo(app,tour,name):
    combo=getattr(tour.editor,name)
    QTest.mouseClick(combo,Qt.LeftButton,pos=combo.rect().center())
    view=combo.view();drain(app,lambda:view.isVisible())
    QTest.qWait(220)
    rect=view.visualRect(combo.model().index(0,0))
    QTest.mouseMove(view.viewport(),rect.center(),delay=50)
    QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=rect.center())
    assert combo.currentIndex()==0,(name,combo.currentIndex(),rect,view.geometry(),combo.isEnabled(),view.isEnabled(),
                                  QApplication.activeModalWidget(),QApplication.activePopupWidget(),view.indexAt(rect.center()).row())
    drain(app,lambda:tour.key!=name)


def pick_one(app,tour,button):
    errors=[]
    def select():
        dialog=tour.picker
        if dialog is None:
            QTimer.singleShot(20,select);return
        try:
            listing=dialog.list
            rect=listing.visualItemRect(listing.item(0))
            QTest.mouseClick(listing.viewport(),Qt.LeftButton,pos=QPoint(25,rect.center().y()))
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        except BaseException as exc:
            errors.append(exc);dialog.reject()
    QTimer.singleShot(100,select)
    QTest.mouseClick(button,Qt.LeftButton)
    assert not errors


def enter_value(app,tour,column,text):
    table=tour.editor.table;row=tour.work_row();item=table.item(row,column)
    assert item.flags() & Qt.ItemIsEditable,(tour.key,row,column,item.text(),int(item.flags()))
    QApplication.setActiveWindow(tour.editor)
    table.setFocus()
    table.setCurrentCell(row,column);table.editItem(item)
    app.processEvents()
    editor=QApplication.focusWidget()
    assert editor is not None and hasattr(editor,"setText"),(tour.key,editor,table.state())
    assert table.isAncestorOf(editor),(tour.key,editor.parentWidget())
    QTest.keyClick(editor,Qt.Key_A,Qt.ControlModifier);QTest.keyClicks(editor,text);QTest.keyClick(editor,Qt.Key_Return)
    drain(app,lambda:item.text()==text)


def test_master_follows_clicks_through_order_history_and_admin(system,app,monkeypatch):
    warnings=[]
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox,"warning",lambda parent,title,text:warnings.append(text))
    manager,admin=system;manager.auth.add_user(admin,"master","password123","Мастер Упаковка")
    user=manager.auth.authenticate("master","password123")
    owner=MainWindow(manager.database("packaging",user),user,manager)
    available=QApplication.primaryScreen().availableGeometry()
    owner.resize(min(1727,available.width()),min(910,available.height()));owner.show()
    try:
        drain(app,lambda:owner._glass_painted,timeout=12)
        QTest.mouseClick(owner.titlebar.help,Qt.LeftButton)
        next(button for button in owner._training_start.findChildren(QPushButton) if button.text()=="Начать!").click()
        tour=owner._master_tour
        assert tour.key=="create" and "administration" in tour.keys
        assert not {"catalog","analytics","users"}.intersection(tour.keys)
        click_lesson(app,tour);drain(app,lambda:tour.key=="date" and tour.editor.isVisible())
        field=tour.editor.order_date
        QTest.mouseClick(field,Qt.LeftButton,pos=field._icon_rect().center())
        popup=field._popup;drain(app,lambda:popup.isVisible() and popup.ready and not popup.cover.isVisible(),timeout=12)
        script(app,popup.view,'document.querySelector("[data-cal=apply]").click()')
        drain(app,lambda:tour.key=="shift")
        for name in ("shift","master","department"):choose_combo(app,tour,name)
        assert tour.key=="employees"
        pick_one(app,tour,tour.editor.add_employee_btn);drain(app,lambda:tour.key=="works")
        pick_one(app,tour,tour.editor.add_work_btn);drain(app,lambda:tour.key=="hours")
        for key,column,value in (("hours",1,"8"),("boxes",5,"12"),("weight",6,"3")):
            assert tour.key==key;enter_value(app,tour,column,value);drain(app,lambda:tour.key!=key)
        assert tour.key=="save"
        QTest.mouseClick(tour.editor.button_box.button(QDialogButtonBox.Ok),Qt.LeftButton)
        assert not warnings,warnings
        drain(app,lambda:tour.key=="edit_hours")
        enter_value(app,tour,1,"9");drain(app,lambda:tour.key=="edit_save")
        QTest.mouseClick(tour.editor.button_box.button(QDialogButtonBox.Ok),Qt.LeftButton)
        assert not warnings,warnings
        drain(app,lambda:tour.key=="history")
        click_lesson(app,tour)
        drain(app,lambda:getattr(owner,"_history_details_dialog",None) is not None)
        assert "8 → 9" in owner._history_details_dialog.findChild(QTextBrowser).toPlainText()
        owner._history_details_dialog.reject();drain(app,lambda:tour.key=="administration")
        click_lesson(app,tour);drain(app,lambda:tour.key.startswith("admin_"))
        seen=[]
        while tour.running:
            seen.append(tour.key)
            next(button for button in tour.coach.card.findChildren(QPushButton) if button.text()=="Далее").click()
            app.processEvents()
        assert {"admin_sync","admin_audit","admin_backup"}.issubset(seen)
        assert manager.database("packaging",user).list_orders()==[]
        assert not list(local_drafts_dir().rglob("*.json"))
        assert not list(manager.root.rglob("new_order*.json"))
    finally:
        if getattr(owner,"_master_tour",None) is not None:owner._master_tour.finish()
        close(owner,app)

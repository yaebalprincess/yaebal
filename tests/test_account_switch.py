"""Switch accounts through the original login, with separate profiles/sessions."""
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QMessageBox

from smartorder import heavy_ui
from smartorder.account_switch import AccountController
from smartorder.config import SettingsStore, UiSettings
from test_liquid_glass import app, glass, system, drain


def dispose(window,app):
    if window is not None and not sip.isdeleted(window):
        window._rc4_exit_confirmed=True;window.close();window.deleteLater()
    app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()


@pytest.mark.parametrize("theme",["light","dark"])
def test_switch_button_asks_centered_question_and_no_keeps_session(glass,app,theme):
    owner,_,_=glass;owner.theme.setChecked(theme=="dark")
    owner.showNormal();owner.resize(780,570);owner.move(0,0);app.processEvents()
    owner.choose_workshop();menu=owner.workshop_menu
    assert menu.switch_account_button.isVisible() and not menu.switch_account_button.icon().isNull()
    assert len(menu.actions())==6
    seen=[];requests=[];owner.accountSwitchRequested.connect(lambda:requests.append(True))
    def inspect():
        box=QApplication.activeModalWidget()
        if not isinstance(box,QMessageBox):QTimer.singleShot(15,inspect);return
        seen.append((box.text(),(box.frameGeometry().center()-owner.frameGeometry().center()).manhattanLength(),
                     box.button(QMessageBox.Yes).text(),box.button(QMessageBox.No).text()))
        box.button(QMessageBox.No).click()
    QTimer.singleShot(30,inspect)
    QTest.mouseClick(menu.switch_account_button,Qt.LeftButton)
    assert seen and seen[0][0]=="Вы уверены, что хотите выйти из аккаунта?"
    assert seen[0][1]<50 and seen[0][2:]==("Да","Нет")
    assert not requests and owner.isVisible() and not owner.session_tracker.closed


def test_relogin_uses_new_permissions_profile_and_session_and_can_repeat(glass,app,monkeypatch):
    owner,manager,admin=glass
    manager.auth.add_user(admin,"economist","password123","Экономист")
    other=manager.auth.authenticate("economist","password123")
    SettingsStore(other.id,other.username).save(UiSettings(theme="dark",zoom=111))
    ids=[];previous=[owner];authenticated=[];quit_calls=[]
    def login_factory(auth):
        dialog=heavy_ui.LoginDialog(auth)
        assert previous[-1].session_tracker.closed
        assert getattr(app,"_smartorder_main_window",None) is None
        assert dialog.parentWidget() is None and not dialog.username_edit.text() and not dialog.password_edit.text()
        name="economist" if not authenticated else "admin"
        def enter():
            dialog.username_edit.setText(name);dialog.password_edit.setText("password123")
            dialog._login();authenticated.append(name)
        QTimer.singleShot(20,enter)
        return dialog
    controller=AccountController(app,manager,owner,login_factory=login_factory,quit_callback=lambda:quit_calls.append(True))
    original_quit=app.quitOnLastWindowClosed()
    monkeypatch.setattr(heavy_ui,"question",lambda *args:QMessageBox.Yes)
    current=owner
    try:
        for name in ("economist","admin"):
            ids.append(current.session_tracker.id)
            current.switch_account()
            drain(app,lambda:controller.window is not None and controller.window.user.username==name and not controller.busy,timeout=20)
            current=controller.window;previous.append(current)
            drain(app,lambda:current._glass_painted,timeout=15)
            assert current.db.user.id==current.user.id and current.session_tracker.id!=ids[-1]
            assert app._smartorder_main_window is current and app.quitOnLastWindowClosed()==original_quit
            if name=="economist":
                assert current.user.role=="Экономист"
                assert not current.create_order_btn.isEnabled()
                assert current.ui_settings.theme=="dark" and current.ui_settings.zoom==111
            with manager.auth.read_conn() as conn:
                assert conn.execute("SELECT ended_at FROM app_sessions WHERE id=?",(ids[-1],)).fetchone()[0]
                assert conn.execute("SELECT COUNT(*) FROM app_sessions WHERE ended_at IS NULL").fetchone()[0]==1
        assert authenticated==["economist","admin"] and not quit_calls
    finally:
        dispose(current,app);controller.deleteLater();app._smartorder_main_window=None


def test_cancel_login_does_not_restore_logged_out_account(glass,app,monkeypatch):
    owner,manager,_=glass;quit_calls=[]
    def login_factory(auth):
        dialog=heavy_ui.LoginDialog(auth);QTimer.singleShot(20,dialog.reject);return dialog
    controller=AccountController(app,manager,owner,login_factory=login_factory,quit_callback=lambda:quit_calls.append(True))
    monkeypatch.setattr(heavy_ui,"question",lambda *args:QMessageBox.Yes)
    tracker=owner.session_tracker
    owner.switch_account();drain(app,lambda:bool(quit_calls))
    assert tracker.closed and controller.window is None and not controller.busy
    assert app._smartorder_main_window is None
    controller.deleteLater()

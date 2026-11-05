import os
import time
import pytest

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QApplication, QMessageBox, QLabel, QTextBrowser
from PyQt5 import sip

from smartorder.db import Database
from smartorder.workshops import WorkshopManager
from smartorder.enterprise_ui import MainWindow, WorkshopDialog, read_news
from smartorder.analytics_ui import EmployeeAnalyticsDialog
from test_rc19_workshops_analytics import order


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ui(app,tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"local"))
    monkeypatch.setenv("SMARTORDER_NETWORK_ROOT",str(tmp_path/"shared"))
    unexpected=[]
    for name in ("warning","critical"):
        monkeypatch.setattr(QMessageBox,name,lambda *args:unexpected.append(args[1:]) or QMessageBox.Ok)
    db=Database(tmp_path/"shared"/"work_orders.db");db.create_first_admin("admin","password123")
    manager=WorkshopManager(db,db.path.parent);admin=manager.auth.authenticate("admin","password123")
    windows=[]
    def create(role="Администратор"):
        if role=="Администратор":user=admin
        else:
            manager.auth.add_user(admin,role,"password123",role);user=manager.auth.authenticate(role,"password123")
        w=MainWindow(db,user,manager);windows.append(w);w.show();app.processEvents();return w
    yield create,manager,admin,unexpected
    for w in windows:
        if sip.isdeleted(w):continue
        w._rc4_exit_confirmed=True;w.close();w.deleteLater()
    app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
    assert not unexpected


def drain(app,condition,timeout=5):
    deadline=time.monotonic()+timeout
    while not condition() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert condition()


def test_analytics_actual_load_theme_zoom_restore_profile_and_about(ui,app):
    create,manager,admin,_=ui
    order(manager,admin,"packaging",10)
    w=create();w.zoom.setValue(120);app.processEvents();w.tabs.setCurrentIndex(4)
    drain(app,lambda:w.analytics is not None and w.analytics.report is not None)
    assert w.analytics.report.employees[0]["fixed_kg"]==20
    assert not w.zoom.isEnabled() and not w._rc18_shortcuts[0].isEnabled()
    assert w.zoom_message.isVisible()
    w._apply_zoom(150);assert w.ui_settings.zoom==120
    w.theme.setChecked(True);assert w.analytics.dark
    w.theme.setChecked(False);assert not w.analytics.dark
    d=EmployeeAnalyticsDialog(w.analytics,w.analytics.report.employees[0]);d.show();app.processEvents()
    assert len(d.rows)==1 and d.scatter.values==[20]
    d.close();d.deleteLater()
    w.tabs.setCurrentIndex(5);app.processEvents()
    labels=[label.text() for label in w.tabs.currentWidget().findChildren(QLabel)]
    assert "Smart Order" in labels and "Enterprise Edition" in labels
    footer=next(b for b in w.tabs.currentWidget().findChildren(QTextBrowser) if "tmbsir" in b.toPlainText())
    assert footer.document().find("tmbsir").charFormat().fontUnderline()
    assert w.zoom.isEnabled() and w.ui_settings.zoom==120


@pytest.mark.parametrize("role,key",[("Мастер Упаковка","packaging"),("Мастер Коптильный Цех","smoking"),("Мастер Цех Сушки","drying"),("Мастер Сычужный цех","rennet"),("Мастер Сыр цех","cheese"),("Мастер Адыгейский Цех","adyghe")])
def test_role_ui_has_own_workshop_and_no_analytics(ui,app,role,key):
    create,manager,admin,_=ui;w=create(role)
    assert w.workshop==key and not w.tabs.isTabEnabled(4)
    assert w.tabs.isTabEnabled(0) and w.tabs.isTabEnabled(2)
    assert '👤' in w.titlebar.badge.text()
    w.tabs.setCurrentIndex(2);app.processEvents();w.tabs.setCurrentIndex(3);app.processEvents()
    assert not w.access_control_check.isEnabled()


def test_switch_workshop_keeps_one_session_and_routes_existing_window(ui,app,monkeypatch):
    create,manager,admin,_=ui;w=create();old=w.session_tracker.id
    w.choose_workshop();app.processEvents()
    action=next(a for a in w.workshop_menu.actions() if a.data()=="smoking")
    w.workshop_menu.close();action.trigger();app.processEvents();new=app._smartorder_main_window
    drain(app,lambda:new.workshop=="smoking" and not new._workshop_switching)
    assert new.workshop=="smoking" and new.db.path.name=="work_orders_koptil.db"
    assert new is w and new.session_tracker.id==old and not w._switching
    new._rc4_exit_confirmed=True;new.close();new.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete)
    with manager.auth.read_conn() as c:
        assert c.execute("SELECT COUNT(*) FROM app_sessions").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM app_session_segments").fetchone()[0]==2


def test_live_news_reads_root_text_as_plain_text(ui):
    create,manager,admin,_=ui
    source=manager.root/"UPDATE_NEWS.txt"
    source.write_text("Новое обновление <b>буквальный текст</b>",encoding="utf-8")
    path,text=read_news()
    assert path==source and "<b>" in text
    source.write_text("Другие новости",encoding="cp1251")
    assert read_news()[1]=="Другие новости"

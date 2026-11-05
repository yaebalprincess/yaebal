from datetime import date
import pytest
from smartorder.db import DatabaseError,StaleOrderError
from smartorder.workshops import SessionTracker
from smartorder.live_ui import notifications,unread_count,mark_read,LiveDiagnosticsDialog
from test_rc19_workshops_analytics import system,order
from test_rc19_ui import app,ui,drain


def notice_order(manager,admin):
    manager.auth.add_user(admin,"Иван","password123","Мастер Коптильный Цех")
    manager.auth.add_user(admin,"Пётр","password123","Мастер Цех Сушки")
    owner=manager.auth.authenticate("Иван","password123");editor=manager.auth.authenticate("Пётр","password123")
    db,_,line,m,d=order(manager,admin,"smoking")
    ownerdb=manager.database("smoking",owner)
    first=ownerdb.save_order(owner,"07-10-2026","Дневная",m,d,[line],comment="Исходный комментарий")
    editdb=manager.database("smoking",editor)
    changed=editdb.save_order(editor,"07-10-2026","Дневная",m,d,[line],comment="Новый комментарий",parent_id=first)
    return owner,editor,ownerdb,first,changed,line,m,d


def test_notification_comments_and_owner_only(system):
    manager,admin=system
    owner,editor,db,first,changed,*_=notice_order(manager,admin)
    notes=notifications(manager,owner)
    assert len(notes)==1 and notes[0]["order_id"]==changed
    assert "оставил комментарий" in notes[0]["message"] and "Новый комментарий" in notes[0]["message"]
    assert notes[0]["version"].endswith(".1") and unread_count(manager,owner)==1
    assert notifications(manager,editor)==[] and notifications(manager,admin)==[]
    mark_read(manager,editor,"smoking",notes[0]["id"])
    assert unread_count(manager,owner)==1
    mark_read(manager,owner,"smoking",notes[0]["id"])
    assert unread_count(manager,owner)==0 and notifications(manager,owner)[0]["read_at"]


def test_self_edits_and_failed_edits_do_not_notify(system):
    manager,admin=system
    owner,editor,db,first,changed,line,m,d=notice_order(manager,admin)
    db.save_order(owner,"07-10-2026","Дневная",m,d,[line],parent_id=changed)
    assert len(notifications(manager,owner))==1
    with pytest.raises(StaleOrderError):manager.database("smoking",editor).save_order(editor,"07-10-2026","Дневная",m,d,[line],parent_id=first)
    assert len(notifications(manager,owner))==1


def test_notifications_survive_login_rename_and_manager_restart(system):
    manager,admin=system
    owner,editor,db,*_=notice_order(manager,admin)
    manager.auth.update_user(admin,owner.id,"Иван Новый","Мастер Коптильный Цех")
    renamed=manager.auth.authenticate("Иван Новый","password123")
    assert len(notifications(manager,renamed))==1


def test_active_instances_distinct_users_close_and_stale(system):
    manager,admin=system
    manager.auth.add_user(admin,"u","password123","Экономист");other=manager.auth.authenticate("u","password123")
    a=SessionTracker(manager,admin,"packaging");b=SessionTracker(manager,admin,"smoking");c=SessionTracker(manager,other,"drying")
    rows=manager.active_sessions(admin)
    assert len(rows)==3 and len({r["user_id"] for r in rows})==2
    a.heartbeat(close=True);assert len(manager.active_sessions(admin))==2
    c.switch("rennet");assert any(r["workshop"]=="rennet" for r in manager.active_sessions(admin))
    with manager.auth.write_conn() as conn:conn.execute("UPDATE app_sessions SET heartbeat_at='2000-01-01T00:00:00+00:00' WHERE id=?",(b.id,))
    assert len(manager.active_sessions(admin))==1
    c.heartbeat(close=True)


def test_diagnostics_renders_live_sessions(ui,app):
    create,manager,admin,_=ui;w=create();second=SessionTracker(manager,admin,"smoking")
    d=LiveDiagnosticsDialog(w);d.show()
    drain(app,lambda:d.active_table.rowCount()==2)
    assert "Открыто экземпляров: 2" in d.active_label.text()
    d.close();d.deleteLater();second.heartbeat(close=True)


def test_bell_no_automatic_popup_and_read_all(ui,app):
    create,manager,admin,_=ui
    owner,editor,db,*_=notice_order(manager,admin)
    from smartorder.enterprise_ui import MainWindow
    w=MainWindow(db,owner,manager);w.show();w.refresh_notifications()
    drain(app,lambda:w._notification_count==1)
    assert "1" in w.titlebar.bell.text() and w.notification_popup is None
    w.show_notifications();app.processEvents();assert w.notification_popup.isVisible()
    w.notification_popup.read_all();drain(app,lambda:w._notification_count==0)
    w._rc4_exit_confirmed=True;w.close();w.deleteLater()

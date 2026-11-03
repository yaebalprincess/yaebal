import os
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from smartorder.db import Database, DatabaseError
from smartorder.domain import OrderLine
from smartorder.security import Permission, DEFAULT_ROLE_PERMISSIONS, SessionUser, WORKSHOP_ROLES
from smartorder.workshops import WorkshopManager, SessionTracker, WORKSHOPS, allowed_workshops
from smartorder.analytics import build_report, export_report, session_summary


@pytest.fixture
def system(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"local"))
    monkeypatch.setenv("SMARTORDER_NETWORK_ROOT",str(tmp_path/"shared"))
    db=Database(tmp_path/"shared"/"work_orders.db")
    db.create_first_admin("admin","password123")
    admin=db.authenticate("admin","password123")
    manager=WorkshopManager(db,db.path.parent)
    return manager,admin


def order(manager,user,key,quantity=10,employee="Иванов Иван Иванович",day="07-10-2026"):
    db=manager.database(key,user)
    master=db.add_employee(user,"Мастер "+key,True)
    worker=db.add_employee(user,employee)
    dep=db.add_department(user,"1. Подразделение "+key)
    work=db.add_work_type(user,"Работа "+key,"001","2")
    line=OrderLine(worker,employee,work,"Работа "+key,"001",Decimal(2),Decimal(8),Decimal(quantity),Decimal(2))
    oid=db.save_order(user,day,"Дневная",master,dep,[line])
    return db,oid,line,master,dep


@pytest.mark.parametrize("role,expected",list(WORKSHOP_ROLES.items()))
def test_master_scopes_and_analytics_denied(system,role,expected):
    manager,admin=system
    manager.auth.add_user(admin,role,"password123",role)
    user=manager.auth.authenticate(role,"password123")
    assert allowed_workshops(user)==expected
    for key in WORKSHOPS:
        if key in expected:assert manager.database(key,user).workshop==key
        else:
            with pytest.raises(DatabaseError):manager.database(key,user)
    with pytest.raises(DatabaseError):build_report(manager,user,date(2026,10,1),date(2026,10,7))


def test_accounting_roles_same_permissions_and_all_shops(system):
    manager,admin=system
    assert DEFAULT_ROLE_PERMISSIONS["Экономист"]==DEFAULT_ROLE_PERMISSIONS["Бухгалтер"]
    for role in ("Бухгалтер","Экономист"):
        manager.auth.add_user(admin,role,"password123",role)
        u=manager.auth.authenticate(role,"password123")
        assert set(allowed_workshops(u))==set(WORKSHOPS)
        with pytest.raises(DatabaseError):manager.database("smoking",u).add_employee(u,"Запрещено")


def test_workshop_independent_catalog_people_orders_and_auth(system):
    manager,admin=system
    pack,oid,_,_,_=order(manager,admin,"packaging")
    smoke=manager.database("smoking",admin)
    assert smoke.get_employees()==[] and smoke.get_work_types()==[] and smoke.list_orders()==[]
    smoke.add_user(admin,"smoke-user","password123","Мастер Коптильный Цех")
    assert manager.auth.authenticate("smoke-user","password123")
    with smoke.backend.read_conn() as conn:assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]==0
    assert pack.get_order(oid)


def test_identity_migration_once_and_production_restore_does_not_restore_users(system,tmp_path):
    manager,admin=system
    pack=manager.database("packaging",admin);backup=tmp_path/"old.db";pack.backup_to(backup)
    manager.auth.add_user(admin,"later","password123","Экономист")
    pack.restore_from(backup)
    assert manager.auth.authenticate("later","password123")
    manager2=WorkshopManager(pack.backend,manager.root)
    assert manager2.auth.authenticate("later","password123")


def test_revoked_login_and_ui_admin_spoof_cannot_write(system):
    manager,admin=system
    manager.auth.add_user(admin,"master","password123","Мастер Упаковка")
    u=manager.auth.authenticate("master","password123");db=manager.database("packaging",u)
    fake=SessionUser(u.id,u.username,"Администратор",frozenset(DEFAULT_ROLE_PERMISSIONS["Администратор"]))
    with pytest.raises(DatabaseError):db.add_user(fake,"intruder","password123","Администратор")
    manager.auth.set_user_active(admin,u.id,False)
    with pytest.raises(DatabaseError):db.add_employee(u,"Не должно сохраниться")


def test_last_revision_only_and_creation_edit_counts(system):
    manager,admin=system
    db,first,line,master,dep=order(manager,admin,"packaging",10)
    line.fixed_boxes=Decimal(15)
    db.save_order(admin,"07-10-2026","Дневная",master,dep,[line],parent_id=first)
    report=build_report(manager,admin,date(2026,1,1),date(2026,12,31))
    assert len(report.orders)==1 and len(report.details)==1
    assert report.employees[0]["fixed_kg"]==30
    assert report.masters[0]["created"]==1 and report.masters[0]["edits"]==1
    assert report.accounts[0]["created"]==1 and report.accounts[0]["edits"]==1


def test_cross_shop_employee_detail_and_filters(system):
    manager,admin=system
    order(manager,admin,"packaging",10);order(manager,admin,"smoking",20)
    report=build_report(manager,admin,date(2026,10,1),date(2026,10,7))
    assert len(report.employees)==1
    assert report.employees[0]["fixed_kg"]==60 and report.employees[0]["orders"]==2
    smoke=build_report(manager,admin,date(2026,10,1),date(2026,10,7),"smoking")
    assert len(smoke.details)==1 and smoke.details[0]["fixed_kg"]==40
    assert build_report(manager,admin,date(2026,9,1),date(2026,9,30)).details==[]


def test_fix_fact_not_combined_and_employee_only_hours_preserved(system):
    manager,admin=system
    db,oid,line,master,dep=order(manager,admin,"packaging",10)
    line.actual_value=Decimal(3)
    empty=OrderLine(employee_id=line.employee_id,employee_name=line.employee_name,hours=Decimal(2))
    db.save_order(admin,"07-10-2026","Дневная",master,dep,[line,empty],parent_id=oid)
    report=build_report(manager,admin,date(2026,10,1),date(2026,10,7))
    employee=report.employees[0]
    assert employee["hours"]==10 and employee["fixed_pay"]==40 and employee["actual_pay"]==6


def test_sessions_switch_and_close_use_one_session(system):
    manager,admin=system
    tracker=SessionTracker(manager,admin,"packaging")
    tracker._started-=20;tracker._segment_started-=10;tracker.switch("smoking")
    tracker._segment_started-=5;tracker.heartbeat(close=True)
    report=build_report(manager,admin,date(2026,1,1),date(2026,12,31))
    assert len(report.sessions)==2
    assert report.accounts[0]["sessions"]==1
    assert report.accounts[0]["total_seconds"]>=15
    with manager.auth.read_conn() as c:assert c.execute("SELECT ended_at FROM app_sessions WHERE id=?",(tracker.id,)).fetchone()[0]
    smoke=build_report(manager,admin,date(2026,1,1),date(2026,12,31),"smoking")
    assert len(smoke.sessions)==1 and smoke.accounts[0]["total_seconds"]>=5


def test_open_sessions_not_in_completed_min_max():
    rows=[{"username":"u","id":"a","seconds_in_period":100,"session_started":"2026-10-01","state":"Завершена"},
          {"username":"u","id":"b","seconds_in_period":1,"session_started":"2026-10-02","state":"Открыта"}]
    s=session_summary(rows)[0]
    assert s["shortest_seconds"]==100 and s["longest_seconds"]==100 and s["last_seconds"]==1


def test_excel_with_charts_values_and_untrusted_string(system,tmp_path):
    manager,admin=system
    order(manager,admin,"packaging",employee='=HYPERLINK("http://invalid.test")')
    report=build_report(manager,admin,date(2026,10,1),date(2026,10,7))
    target=tmp_path/"analytics.xlsx";export_report(target,report,True)
    wb=load_workbook(target)
    assert len(wb["Графики"]._charts)==6
    assert wb["Сотрудники"]["A2"].data_type=="s"
    assert wb["Сотрудники"]["D2"].value==20
    assert len(wb["Детализация"]["A"] )==2
    assert wb["Сотрудники"].freeze_panes=="A2"
    plain=tmp_path/"plain.xlsx";export_report(plain,report,False)
    assert "Графики" not in load_workbook(plain).sheetnames


def test_report_missing_db_does_not_create_it(system):
    manager,admin=system
    manager.path_for("cheese").unlink()
    report=build_report(manager,admin,date(2026,10,1),date(2026,10,7))
    assert "Сыр цех" in report.missing_workshops
    assert not manager.path_for("cheese").exists()


def test_all_labelled_databases_created_without_shared_data(system):
    manager,admin=system
    expected={"work_orders_ypak.db","work_orders_koptil.db","work_orders_sushka.db","work_orders_sychug.db","work_orders_syr.db","work_orders_adyg.db"}
    assert {manager.path_for(k).name for k in WORKSHOPS}==expected
    assert all(manager.path_for(k).exists() for k in WORKSHOPS)


def test_config_drafts_backups_scoped(system,monkeypatch):
    from smartorder.config import set_active_workshop,local_drafts_dir,shared_dirs,database_path
    manager,admin=system
    set_active_workshop("smoking");s=local_drafts_dir();paths=shared_dirs()
    assert paths["manual"].is_relative_to(manager.root/"workshops"/"smoking")
    assert database_path()==manager.path_for("smoking")
    set_active_workshop("packaging")
    assert s!=local_drafts_dir()


def test_analytics_invalid_range_rejected(system):
    manager,admin=system
    with pytest.raises(ValueError):build_report(manager,admin,date(2026,10,8),date(2026,10,7))

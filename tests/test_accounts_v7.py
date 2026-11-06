from datetime import datetime,timedelta
import json
import pytest
from smartorder.db import Database,DatabaseError
from smartorder.security import Permission,ROLES,split_roles
from smartorder.workshops import WorkshopManager
from smartorder.account_store import activate_due


@pytest.fixture
def accounts(tmp_path,monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"local"));monkeypatch.setenv("SMARTORDER_NETWORK_ROOT",str(tmp_path/"shared"))
    source=Database(tmp_path/"shared"/"work_orders.db");source.create_first_admin("admin","password123")
    manager=WorkshopManager(source,source.path.parent);admin=manager.auth.authenticate("admin","password123")
    return manager,admin


def test_old_analyst_role_is_migrated_without_changing_password(accounts):
    manager,admin=accounts
    manager.auth.add_user(admin,"legacy","password123","Экономист")
    with manager.auth.write_conn() as conn:
        conn.execute("UPDATE users SET role='Аналитик' WHERE username='legacy'")
        conn.execute("DELETE FROM db_meta WHERE key='account_options_v7'")
    fresh=Database(manager.auth.path);fresh.ensure_account_schema();user=fresh.authenticate("legacy","password123")
    assert user.role=="Экономист" and "Аналитик" not in ROLES
    assert user.can(Permission.NOTIFICATIONS_VIEW) and not user.can(Permission.EMPLOYEES_VIEW)
    assert split_roles("Аналитик;Экономист")==("Экономист",)
    with fresh.read_conn() as conn:assert conn.execute("SELECT role FROM users WHERE id=?",(user.id,)).fetchone()[0]=="Экономист"


def test_explicit_grants_and_revocation_enforced_on_existing_session(accounts):
    manager,admin=accounts
    rights=[Permission.EMPLOYEES_VIEW,Permission.EMPLOYEES_CREATE]
    manager.auth.add_user(admin,"custom","password123","Экономист",permissions=rights)
    user=manager.auth.authenticate("custom","password123");db=manager.database("packaging",user)
    db.add_employee(user,"Работник",False)
    manager.auth.update_user(admin,user.id,user.username,user.role,permissions=[Permission.EMPLOYEES_VIEW])
    assert user.can(Permission.EMPLOYEES_CREATE)
    with pytest.raises(DatabaseError,match="прав"):db.add_employee(user,"Запрещено",False)
    assert [row[1] for row in db.get_employees(False)]==["Работник"]
    assert manager.auth.authenticate("custom","password123").permissions=={Permission.EMPLOYEES_VIEW}


def test_scheduled_user_cannot_sign_in_until_due(accounts):
    manager,admin=accounts;when=datetime.now()+timedelta(days=2)
    manager.auth.add_user(admin,"future","password123","Экономист",activate_at=when.isoformat(timespec="seconds"))
    assert manager.auth.authenticate("future","password123") is None
    row=next(r for r in manager.auth.list_users() if r[1]=="future")
    assert not row[3] and row[4] and manager.auth.user_options(row[0])["activate_at"]
    activate_due(manager.auth,when+timedelta(seconds=1))
    assert manager.auth.authenticate("future","password123") is not None
    assert manager.auth.user_options(row[0])["activate_at"] is None


def test_manual_disable_cancels_scheduled_activation(accounts):
    manager,admin=accounts;when=datetime.now()+timedelta(days=2)
    manager.auth.add_user(admin,"future","password123","Экономист",activate_at=when.isoformat())
    uid=next(r[0] for r in manager.auth.list_users() if r[1]=="future")
    manager.auth.set_user_active(admin,uid,False);activate_due(manager.auth,when+timedelta(days=1))
    assert manager.auth.authenticate("future","password123") is None


def test_last_admin_and_permission_assignment_are_protected(accounts):
    manager,admin=accounts
    with pytest.raises(DatabaseError,match="последнего"):
        manager.auth.update_user(admin,admin.id,admin.username,admin.role,permissions=[])
    manager.auth.add_user(admin,"operator","password123","Экономист",permissions=[Permission.USERS_MANAGE])
    operator=manager.auth.authenticate("operator","password123")
    with pytest.raises(DatabaseError,match="прав"):
        manager.auth.add_user(operator,"escalated","password123","Администратор")
    with pytest.raises(DatabaseError,match="прав"):
        manager.auth.update_user(operator,admin.id,admin.username,admin.role,permissions=[])


def test_own_shared_profile_survives_new_database_client(accounts):
    manager,admin=accounts
    manager.auth.add_user(admin,"other","password123","Экономист")
    other=manager.auth.authenticate("other","password123")
    manager.auth.save_personalization(admin,True,{"theme":"dark"})
    fresh=Database(manager.auth.path)
    assert fresh.get_personalization(admin)["payload"]=={"theme":"dark"}
    assert fresh.get_personalization(other) is None
    fresh.save_personalization(other,True,{"language":"kk"})
    assert manager.auth.get_personalization(admin)["payload"]=={"theme":"dark"}

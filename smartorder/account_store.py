"""Account options and portable preferences in the shared identity database."""
import json
from datetime import datetime
from .security import ALL_PERMISSIONS, Permission, SessionUser, split_roles

UNSET = object()


def ensure_accounts(db):
    if getattr(db, "_account_schema_ready", False):
        return
    with db.read_conn() as conn:
        marker = conn.execute("SELECT value FROM db_meta WHERE key='account_options_v7'").fetchone()
    if not marker:
        with db.write_conn() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS account_options(user_id INTEGER PRIMARY KEY, permissions_json TEXT, activate_at TEXT, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_account_activation ON account_options(activate_at)")
            conn.execute("CREATE TABLE IF NOT EXISTS user_personalization(user_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)")
            for row in conn.execute("SELECT id,role FROM users WHERE role LIKE '%Аналитик%'").fetchall():
                conn.execute("UPDATE users SET role=? WHERE id=?", (";".join(split_roles(row[1])), row[0]))
            conn.execute("INSERT OR REPLACE INTO db_meta(key,value) VALUES('account_options_v7','1')")
    db._account_schema_ready = True


def normalized_permissions(value):
    if value is None:
        return None
    if not isinstance(value, (list, tuple, set, frozenset)) or any(p not in ALL_PERMISSIONS for p in value):
        raise ValueError("Неизвестное право доступа")
    return sorted(set(value))


def options(db, user_id):
    ensure_accounts(db)
    with db.read_conn() as conn:
        row = conn.execute("SELECT permissions_json,activate_at FROM account_options WHERE user_id=?", (int(user_id),)).fetchone()
    return {"permissions": json.loads(row[0]) if row and row[0] is not None else None,
            "activate_at": row[1] if row else None}


def effective_permissions(db, user_id, role, conn=None):
    ensure_accounts(db)
    if conn is None:
        with db.read_conn() as reader:
            return effective_permissions(db, user_id, role, reader)
    row = conn.execute("SELECT permissions_json FROM account_options WHERE user_id=?", (int(user_id),)).fetchone()
    if row and row[0] is not None:
        return frozenset(normalized_permissions(json.loads(row[0])))
    return db.role_permissions(role)


def activate_due(db, now=None):
    ensure_accounts(db)
    cutoff = (now or datetime.now()).isoformat(timespec="seconds")
    with db.read_conn() as conn:
        due = conn.execute("SELECT 1 FROM account_options WHERE activate_at IS NOT NULL AND activate_at<=? LIMIT 1", (cutoff,)).fetchone()
    if due:
        with db.write_conn() as conn:
            conn.execute("UPDATE users SET is_active=1 WHERE id IN (SELECT user_id FROM account_options WHERE activate_at IS NOT NULL AND activate_at<=?)", (cutoff,))
            conn.execute("UPDATE account_options SET activate_at=NULL WHERE activate_at IS NOT NULL AND activate_at<=?", (cutoff,))


def validate_actor(db, actor, permission=None, conn=None):
    from .db import DatabaseError
    ensure_accounts(db)
    if conn is None:
        with db.read_conn() as reader:return validate_actor(db,actor,permission,reader)
    if actor.id==0 and not conn.execute("SELECT access_control_enabled FROM settings WHERE id=1").fetchone()[0]:
        current=actor.permissions
    else:
        row=conn.execute("SELECT username,role,is_active FROM users WHERE id=?",(actor.id,)).fetchone()
        if not row or not row[2] or row[0]!=actor.username or split_roles(row[1])!=actor.roles:
            raise DatabaseError("Учётная запись изменена или отключена. Войдите заново.")
        current=effective_permissions(db,actor.id,row[1],conn)
    if permission and permission not in current:raise DatabaseError("Недостаточно прав для этой операции")
    return current


def require_manage_target(db,conn,current,user_id):
    from .db import DatabaseError
    if Permission.PERMISSIONS_MANAGE in current:return
    target=conn.execute("SELECT role FROM users WHERE id=?",(user_id,)).fetchone()
    if target and not set(effective_permissions(db,user_id,target[0],conn))<=set(current):
        raise DatabaseError("Нет прав на изменение более привилегированной учётной записи")


def activation_value(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    if parsed <= datetime.now():
        raise ValueError("Дата активации должна быть в будущем")
    return parsed.isoformat(timespec="seconds")


def guard_last_admin(db, conn, user_id, role, active, permissions):
    from .db import DatabaseError
    old = conn.execute("SELECT role,is_active FROM users WHERE id=?", (user_id,)).fetchone()
    if not old or not old[1] or "Администратор" not in split_roles(old[0]):
        return
    effective = db.role_permissions(role) if permissions is None else set(permissions)
    needed = {Permission.USERS_MANAGE, Permission.PERMISSIONS_MANAGE}
    if active and "Администратор" in split_roles(role) and needed <= set(effective):
        return
    for candidate in conn.execute("SELECT id,role FROM users WHERE is_active=1 AND id<>?", (user_id,)).fetchall():
        if "Администратор" in split_roles(candidate[1]) and needed <= set(effective_permissions(db, candidate[0], candidate[1], conn)):
            return
    raise DatabaseError("Нельзя отключить или ограничить последнего активного администратора")


def get_personalization(db, actor):
    validate_actor(db, actor)
    with db.read_conn() as conn:
        row = conn.execute("SELECT enabled,payload,revision,updated_at FROM user_personalization WHERE user_id=?", (actor.id,)).fetchone()
    return {"enabled": bool(row[0]), "payload": json.loads(row[1]), "revision": row[2], "updated_at": row[3]} if row else None


def save_personalization(db, actor, enabled, payload):
    validate_actor(db, actor)
    text = json.dumps(payload, ensure_ascii=False)
    if len(text.encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("Конфигурация слишком велика: максимум 8 МБ")
    with db.write_conn() as conn:
        conn.execute("INSERT INTO user_personalization(user_id,enabled,payload,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled,payload=excluded.payload,updated_at=excluded.updated_at,revision=revision+1", (actor.id, int(bool(enabled)), text, datetime.now().isoformat(timespec="seconds")))


def account_snapshot(db,user_id):
    ensure_accounts(db)
    with db.read_conn() as conn:
        row=conn.execute("SELECT u.username,u.role,u.is_active,o.permissions_json,o.activate_at FROM users u LEFT JOIN account_options o ON o.user_id=u.id WHERE u.id=?",(user_id,)).fetchone()
    if row and not row[2] and row[4] and row[4]<=datetime.now().isoformat(timespec="seconds"):
        activate_due(db);return account_snapshot(db,user_id)
    if not row or not row[2]:return None
    permissions=frozenset(normalized_permissions(json.loads(row[3]))) if row[3] is not None else db.role_permissions(row[1])
    return SessionUser(int(user_id),row[0],";".join(split_roles(row[1])),permissions)

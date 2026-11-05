"""Separate production databases, shared authentication and session telemetry.

SQLite stays in DELETE journal mode: no WAL files on an SMB share. Authentication
is never copied to production databases. Existing work_orders.db is kept in place.
"""
from __future__ import annotations

import threading
import time
import uuid
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import network_root, base_database_path, workshop_root, WORKSHOP_DB_FILES
from .db import Database, DatabaseError
from .security import SessionUser, Permission, WORKSHOP_ROLES, DEFAULT_ROLE_PERMISSIONS, ANALYTICS_ROLES, ANALYTICS_ONLY_ROLES, split_roles

WORKSHOPS = {
    "packaging": "Упаковка",
    "smoking": "Коптильный",
    "drying": "Сушка",
    "rennet": "Сычужный",
    "cheese": "Сыр цех",
    "adyghe": "Адыгейский",
}


def allowed_workshops(user: SessionUser) -> tuple[str, ...]:
    roles=split_roles(user.role)
    # Full analytics roles can compare every production workspace. A user may
    # also carry an analytics-only role alongside one or more workshop roles;
    # in that case preserve the explicit workshop assignment instead of
    # silently collapsing it to packaging.
    if any(role in (ANALYTICS_ROLES - ANALYTICS_ONLY_ROLES) for role in roles):
        return tuple(WORKSHOPS)
    result=[]
    for role in roles:
        for key in WORKSHOP_ROLES.get(role, ()):
            if key not in result: result.append(key)
    if not result and any(role in ANALYTICS_ONLY_ROLES for role in roles):
        return ("packaging",)
    return tuple(result)


def utc_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class WorkshopManager:
    def __init__(self, auth: Database, root: Path | None = None):
        self.root = Path(root or network_root())
        production_path = self.root / "databases" / WORKSHOP_DB_FILES["packaging"]
        self._migrate_production(auth,production_path)
        production = auth if auth.path.resolve()==production_path.resolve() else Database(production_path)
        # Move the shared login authority out of every production backup. Copy
        # hashes and IDs once; leave the original database and credentials intact.
        self.auth = Database(self.root / "databases" / "identity.db")
        self._migrate_identity(auth)
        self._databases = {"packaging": production}
        self._lock = threading.RLock()
        self._ensure_sessions()
        # Create all six labelled files once, even before a user visits a shop.
        # Existing files use the lightweight compatibility probe, never a reset.
        for key in WORKSHOPS:
            if key not in self._databases:
                self._databases[key] = Database(self.path_for(key))
        from .order_files import ArchivePublisher
        self.archive_publisher = ArchivePublisher(self.root)

    def path_for(self, key: str) -> Path:
        if key not in WORKSHOPS:
            raise DatabaseError("Неизвестный цех")
        return self._databases["packaging"].path if key == "packaging" else self.root / "databases" / WORKSHOP_DB_FILES[key]

    @staticmethod
    def _migrate_production(source,target):
        if source.path.resolve()==target.resolve() or target.exists():return
        target.parent.mkdir(parents=True,exist_ok=True)
        lock=target.with_suffix(".migration.lock")
        acquired=False
        for _ in range(40):
            if target.exists():return
            try:
                fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd);acquired=True;break
            except FileExistsError:time.sleep(.15)
        if not acquired:raise DatabaseError("Первый перенос базы выполняется другим клиентом. Повторите запуск. Если запуск прерван, сисадмин должен проверить файл .migration.lock.")
        tmp=target.with_name("."+target.name+"."+uuid.uuid4().hex+".tmp")
        try:
            if not target.exists():
                source.backup_to(tmp,verify=True)
                os.replace(tmp,target)
        finally:
            tmp.unlink(missing_ok=True);lock.unlink(missing_ok=True)

    def _migrate_identity(self, legacy):
        with self.auth.read_conn() as conn:
            if conn.execute("SELECT 1 FROM db_meta WHERE key='rc19_identity_migrated'").fetchone():
                return
        with legacy.read_conn() as conn:
            users = [tuple(r) for r in conn.execute("SELECT id,username,password_hash,role,is_active FROM users")]
            settings = conn.execute("SELECT access_control_enabled FROM settings WHERE id=1").fetchone()
        with self.auth.write_conn() as conn:
            if conn.execute("SELECT 1 FROM db_meta WHERE key='rc19_identity_migrated'").fetchone():
                return
            if not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                conn.executemany("INSERT INTO users(id,username,password_hash,role,is_active) VALUES(?,?,?,?,?)",users)
                if settings:conn.execute("UPDATE settings SET access_control_enabled=? WHERE id=1",(settings[0],))
            conn.execute("INSERT INTO db_meta(key,value) VALUES('rc19_identity_migrated','1')")

    def validate_user(self, user: SessionUser) -> None:
        # Disabled access control intentionally allows the pre-existing system mode.
        if user.id == 0:
            if self.auth.is_access_control_enabled():
                raise DatabaseError("Разрешительный режим включён. Перезапустите программу и войдите.")
            return
        with self.auth.read_conn() as conn:
            row = conn.execute("SELECT username,role,is_active FROM users WHERE id=?", (user.id,)).fetchone()
        if not row or not row[2] or row[0] != user.username or row[1] != user.role:
            raise DatabaseError("Учётная запись изменена или отключена. Войдите заново.")

    def require(self, user: SessionUser, permission: str) -> None:
        self.validate_user(user)
        if not user.can(permission):
            raise DatabaseError("Недостаточно прав для этой операции")

    def database(self, key: str, user: SessionUser) -> "WorkshopDatabase":
        self.validate_user(user)
        if key not in allowed_workshops(user):
            raise DatabaseError("Нет доступа к выбранному цеху")
        with self._lock:
            if key not in self._databases:
                self._databases[key] = Database(self.path_for(key))
            backend = self._databases[key]
        return WorkshopDatabase(self, backend, user, key)

    def _ensure_sessions(self):
        try:
            with self.auth.read_conn() as conn:
                conn.execute("SELECT id,computer,process_id,client_path FROM app_sessions LIMIT 1").fetchone()
                conn.execute("SELECT id FROM app_session_segments LIMIT 1").fetchone()
            return
        except Exception:
            pass
        with self.auth.write_conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS app_sessions (
                id TEXT PRIMARY KEY, user_id INTEGER, username TEXT NOT NULL,
                role TEXT NOT NULL, started_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL,
                ended_at TEXT, duration_seconds REAL NOT NULL DEFAULT 0,
                workshop TEXT NOT NULL)""")
            for column,ddl in (("computer","TEXT"),("process_id","INTEGER"),("client_path","TEXT")):
                Database._add_column(conn,"app_sessions",column,ddl)
            conn.execute("""CREATE TABLE IF NOT EXISTS app_session_segments (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, workshop TEXT NOT NULL,
                started_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL, ended_at TEXT,
                duration_seconds REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(session_id) REFERENCES app_sessions(id))""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_user ON app_sessions(user_id,started_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_segment_session ON app_session_segments(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_heartbeat ON app_sessions(ended_at,heartbeat_at)")

    def active_sessions(self,user,max_age=150):
        from datetime import timedelta
        self.require(user,Permission.ADMIN_VIEW)
        cutoff=(datetime.now(timezone.utc)-timedelta(seconds=max_age)).isoformat(timespec="seconds")
        with self.auth.read_conn() as conn:
            rows=[dict(r) for r in conn.execute("""SELECT id,user_id,username,role,computer,process_id,client_path,workshop,
                started_at,heartbeat_at,duration_seconds FROM app_sessions
                WHERE ended_at IS NULL AND heartbeat_at>=? ORDER BY started_at DESC""",(cutoff,))]
        for r in rows:r["workshop_name"]=WORKSHOPS.get(r["workshop"],r["workshop"])
        return rows


_AUTH_METHODS = {"list_users", "add_user", "update_user", "delete_user", "set_user_active",
                 "authenticate", "has_users", "startup_bundle", "is_access_control_enabled",
                 "set_access_control", "role_permissions", "set_role_permissions"}
_MUTATIONS = {
    "set_work_fact_unit": Permission.CATALOG_EDIT,
    "save_order": Permission.ORDERS_CREATE,
    "add_employee": Permission.EMPLOYEES_CREATE, "update_employee": Permission.EMPLOYEES_EDIT,
    "delete_employee": Permission.EMPLOYEES_DELETE, "import_people": Permission.EMPLOYEES_IMPORT,
    "add_department": Permission.EMPLOYEES_CREATE, "update_department": Permission.EMPLOYEES_EDIT,
    "delete_department": Permission.EMPLOYEES_DELETE, "import_departments": Permission.EMPLOYEES_IMPORT,
    "add_work_type": Permission.CATALOG_CREATE, "update_work_type": Permission.CATALOG_EDIT,
    "delete_work_type": Permission.CATALOG_DELETE, "import_work_types": Permission.CATALOG_IMPORT,
    "add_user": Permission.USERS_MANAGE, "update_user": Permission.USERS_MANAGE,
    "delete_user": Permission.USERS_MANAGE, "set_user_active": Permission.USERS_MANAGE,
    "restore_soft_deleted": Permission.USERS_MANAGE, "restore_from": Permission.USERS_MANAGE,
    "set_access_control": Permission.USERS_MANAGE, "set_role_permissions": Permission.PERMISSIONS_MANAGE,
    "acquire_edit_lock": Permission.ORDERS_EDIT,
}


class WorkshopDatabase:
    """Compatibility facade bound to one immutable workshop and real login.

    The UI sometimes creates a temporary administrator object while laying out
    controls. Authorization here always uses the original authenticated user.
    """
    def __init__(self, manager, backend, user, key):
        self.manager, self.backend, self.user, self.workshop = manager, backend, user, key
        self.path = backend.path

    def __getattr__(self, name):
        target = self.manager.auth if name in _AUTH_METHODS else self.backend
        value = getattr(target, name)
        if name not in _MUTATIONS:
            return value
        def guarded(*args, **kwargs):
            permission = _MUTATIONS[name]
            if name == "save_order" and (kwargs.get("parent_id") is not None or len(args)>8 and args[8] is not None):
                permission = Permission.ORDERS_EDIT
            self.manager.require(self.user, permission)
            if self.workshop not in allowed_workshops(self.user):
                raise DatabaseError("Нет доступа к цеху")
            result = value(*args, **kwargs)
            if name == "save_order":
                self.manager.archive_publisher.request(self.workshop,self.backend)
            return result
        return guarded


class SessionTracker:
    """One application session with separate workshop visits; crash capped at heartbeat."""
    def __init__(self, manager: WorkshopManager, user: SessionUser, key: str):
        self.manager, self.user = manager, user
        self.id = uuid.uuid4().hex
        self.segment_id = uuid.uuid4().hex
        self.key = key
        self._started = self._segment_started = time.monotonic()
        self._lock = threading.Lock()
        self.closed = False
        stamp = utc_text()
        with manager.auth.write_conn() as conn:
            conn.execute("INSERT INTO app_sessions(id,user_id,username,role,started_at,heartbeat_at,workshop,computer,process_id,client_path) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (self.id, user.id, user.username, user.role, stamp, stamp, key,socket.gethostname(),os.getpid(),sys.executable))
            self._insert_segment(conn, stamp)

    def _insert_segment(self, conn, stamp):
        conn.execute("INSERT INTO app_session_segments(id,session_id,workshop,started_at,heartbeat_at) VALUES(?,?,?,?,?)",
                     (self.segment_id, self.id, self.key, stamp, stamp))

    def heartbeat(self, close=False):
        with self._lock:
            if self.closed:
                return
            stamp, now = utc_text(), time.monotonic()
            with self.manager.auth.write_conn() as conn:
                conn.execute("UPDATE app_sessions SET heartbeat_at=?,duration_seconds=?,ended_at=? WHERE id=?",
                             (stamp, max(0, now-self._started), stamp if close else None, self.id))
                conn.execute("UPDATE app_session_segments SET heartbeat_at=?,duration_seconds=?,ended_at=? WHERE id=?",
                             (stamp, max(0, now-self._segment_started), stamp if close else None, self.segment_id))
            self.closed = close

    def switch(self, key):
        if key not in allowed_workshops(self.user):
            raise DatabaseError("Нет доступа к цеху")
        with self._lock:
            stamp, now = utc_text(), time.monotonic()
            old_segment, new_segment = self.segment_id, uuid.uuid4().hex
            with self.manager.auth.write_conn() as conn:
                conn.execute("UPDATE app_session_segments SET heartbeat_at=?,ended_at=?,duration_seconds=? WHERE id=?",
                             (stamp, stamp, max(0, now-self._segment_started), old_segment))
                conn.execute("INSERT INTO app_session_segments(id,session_id,workshop,started_at,heartbeat_at) VALUES(?,?,?,?,?)",
                             (new_segment, self.id, key, stamp, stamp))
                conn.execute("UPDATE app_sessions SET workshop=?,heartbeat_at=?,duration_seconds=? WHERE id=?",
                             (key, stamp, max(0, now-self._started), self.id))
            self.key, self.segment_id, self._segment_started = key, new_segment, now

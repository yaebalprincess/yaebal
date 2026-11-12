from __future__ import annotations

import os
import json
import hashlib
import socket
import sqlite3
import threading
import time
import uuid
import statistics
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .domain import OrderLine, dec
from .account_store import UNSET
from .security import Permission
from .security import (
    ALL_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
    SessionUser,
    hash_password,
    verify_password,
    split_roles,
)

SCHEMA_VERSION = 300
DT_FMT = "%d-%m-%Y %H:%M:%S"
RECENT_DELETED_DAYS = 30
ORDER_RETENTION_DAYS = 365


def now_text() -> str:
    return datetime.now().strftime(DT_FMT)


def department_sort_key(name: object) -> tuple[int, int, str]:
    """Natural numeric order for department names prefixed as ``N. Name``."""
    text = str(name or "").strip()
    prefix, sep, _rest = text.partition(".")
    if sep and prefix.strip().isdigit():
        return (0, int(prefix.strip()), text.casefold().replace("ё", "е"))
    return (1, 10**9, text.casefold().replace("ё", "е"))


def is_busy(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "locked" in text or "busy" in text


class DatabaseError(RuntimeError):
    pass


class StaleOrderError(DatabaseError):
    pass


class Database:
    """Small SQLite repository optimized for short SMB transactions.

    Important rules:
    - no WAL on network shares;
    - one transaction per business operation, never commit per row;
    - reference lists are cached in memory;
    - all writes use BEGIN IMMEDIATE with bounded retries.
    """

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._cache: dict[str, tuple[float, list]] = {}
        self._cache_lock = threading.Lock()
        self._legacy_compatible = False
        self._optional_schema_ready = False

        # Fast network startup: one metadata request, not exists()+stat()+mkdir().
        # Existing shared databases are never modified during ordinary startup.
        try:
            st = self.path.stat()
            new_db = st.st_size == 0
        except FileNotFoundError:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            new_db = True

        if new_db:
            self._ensure_schema()
            self._write_local_compat_marker()
        elif self._local_compat_marker_valid() and self._basic_existing_db_probe():
            # Known-compatible shared DB: one SELECT is enough on subsequent launches.
            self._legacy_compatible = True
        elif self._schema_ready_fast():
            self._optional_schema_ready = True
            self._write_local_compat_marker()
        elif self._legacy_schema_compatible():
            self._legacy_compatible = True
            self._write_local_compat_marker()
        else:
            # Truly old/incomplete schema: bounded migration path.
            self._ensure_schema()
            self._write_local_compat_marker()

    def _compat_marker_path(self) -> Path:
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".smartorder"))
        ident = hashlib.sha256(str(self.path).casefold().encode("utf-8", errors="ignore")).hexdigest()[:20]
        folder = base / "SmartOrder" / "state" / "schema_compat"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{ident}.txt"

    def _local_compat_marker_valid(self) -> bool:
        try:
            return self._compat_marker_path().read_text(encoding="ascii").strip() == str(SCHEMA_VERSION)
        except Exception:
            return False

    def _write_local_compat_marker(self) -> None:
        try:
            self._compat_marker_path().write_text(str(SCHEMA_VERSION), encoding="ascii")
        except Exception:
            pass

    def _invalidate_local_compat_marker(self) -> None:
        try:
            self._compat_marker_path().unlink(missing_ok=True)
        except Exception:
            pass

    def _basic_existing_db_probe(self) -> bool:
        conn = None
        try:
            conn = self._connect(0.8)
            conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            return True
        except Exception:
            return False
        finally:
            if conn is not None:
                conn.close()

    def _schema_ready_fast(self) -> bool:
        """One read-only-ish probe on normal startup; migrations run only when needed."""
        if not self.path.exists():
            return False
        conn = None
        try:
            conn = self._connect(0.8)
            row = conn.execute(
                "SELECT value FROM db_meta WHERE key='smartorder_lite_schema'"
            ).fetchone()
            return bool(row and str(row[0]) == str(SCHEMA_VERSION))
        except Exception:
            return False
        finally:
            if conn is not None:
                conn.close()

    def _legacy_schema_compatible(self) -> bool:
        """Single-query compatibility probe for an existing Full/v151 database.

        SQLite validates every referenced table/column while preparing this query,
        even when a table is empty.  That replaces the old sqlite_master + many
        PRAGMA table_info round-trips which are expensive over SMB.
        """
        probe_sql = """
            SELECT
              (SELECT id FROM users LIMIT 1),
              (SELECT username FROM users LIMIT 1),
              (SELECT password_hash FROM users LIMIT 1),
              (SELECT role FROM users LIMIT 1),
              (SELECT is_active FROM users LIMIT 1),
              (SELECT id FROM settings LIMIT 1),
              (SELECT access_control_enabled FROM settings LIMIT 1),
              (SELECT id FROM employees LIMIT 1),
              (SELECT name FROM employees LIMIT 1),
              (SELECT is_master FROM employees LIMIT 1),
              (SELECT id FROM departments LIMIT 1),
              (SELECT name FROM departments LIMIT 1),
              (SELECT id FROM work_types LIMIT 1),
              (SELECT name FROM work_types LIMIT 1),
              (SELECT code FROM work_types LIMIT 1),
              (SELECT price FROM work_types LIMIT 1),
              (SELECT is_favorite FROM work_types LIMIT 1),
              (SELECT work_type_id FROM work_type_prices LIMIT 1),
              (SELECT id FROM work_orders LIMIT 1),
              (SELECT order_date FROM work_orders LIMIT 1),
              (SELECT shift_type FROM work_orders LIMIT 1),
              (SELECT master_id FROM work_orders LIMIT 1),
              (SELECT department_id FROM work_orders LIMIT 1),
              (SELECT version FROM work_orders LIMIT 1),
              (SELECT status FROM work_orders LIMIT 1),
              (SELECT comment FROM work_orders LIMIT 1),
              (SELECT order_id FROM work_order_items LIMIT 1),
              (SELECT employee_id FROM work_order_items LIMIT 1),
              (SELECT work_type_id FROM work_order_items LIMIT 1),
              (SELECT work_name_snapshot FROM work_order_items LIMIT 1),
              (SELECT work_code_snapshot FROM work_order_items LIMIT 1),
              (SELECT price_snapshot FROM work_order_items LIMIT 1),
              (SELECT order_id FROM work_order_layout_rows LIMIT 1),
              (SELECT row_index FROM work_order_layout_rows LIMIT 1),
              (SELECT employee_name_snapshot FROM work_order_layout_rows LIMIT 1),
              (SELECT work_name_snapshot FROM work_order_layout_rows LIMIT 1),
              (SELECT work_code_snapshot FROM work_order_layout_rows LIMIT 1),
              (SELECT price_snapshot FROM work_order_layout_rows LIMIT 1),
              (SELECT fixed_total FROM work_order_layout_rows LIMIT 1),
              (SELECT actual_value FROM work_order_layout_rows LIMIT 1),
              (SELECT payment FROM work_order_layout_rows LIMIT 1),
              (SELECT id FROM audit_log LIMIT 1),
              (SELECT key FROM db_meta LIMIT 1),
              (SELECT value FROM db_meta LIMIT 1)
        """
        conn = None
        try:
            conn = self._connect(1.0)
            conn.execute(probe_sql).fetchone()
            return True
        except sqlite3.OperationalError as exc:
            if is_busy(exc):
                for attempt in range(5):
                    time.sleep(min(0.08 + attempt * 0.08, 0.35))
                    try:
                        if conn is not None:
                            conn.close()
                        conn = self._connect(1.2)
                        conn.execute(probe_sql).fetchone()
                        return True
                    except sqlite3.OperationalError as retry_exc:
                        if not is_busy(retry_exc):
                            return False
                raise DatabaseError(
                    "Общая база временно занята другим пользователем. Повторите запуск через несколько секунд."
                ) from exc
            return False
        except Exception:
            return False
        finally:
            if conn is not None:
                conn.close()

    def _ensure_optional_schema(self) -> None:
        """Create only LiteCore service tables, lazily, never on ordinary startup."""
        if self._optional_schema_ready:
            return
        with self.write_conn(retries=6) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS permissions (
                    code TEXT PRIMARY KEY,
                    label TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS role_permissions (
                    role TEXT NOT NULL,
                    permission_code TEXT NOT NULL,
                    PRIMARY KEY(role, permission_code)
                );
                CREATE TABLE IF NOT EXISTS work_order_edit_locks (
                    lock_key TEXT PRIMARY KEY,
                    order_id INTEGER,
                    username TEXT NOT NULL,
                    role TEXT,
                    computer TEXT,
                    process_id INTEGER,
                    token TEXT NOT NULL,
                    acquired_at REAL NOT NULL,
                    heartbeat_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lock_heartbeat ON work_order_edit_locks(heartbeat_at);
                """
            )
            from .security import PERMISSION_LABELS
            for code in ALL_PERMISSIONS:
                conn.execute(
                    "INSERT OR IGNORE INTO permissions(code,label) VALUES(?,?)",
                    (code, PERMISSION_LABELS.get(code, code)),
                )
            count = conn.execute("SELECT COUNT(*) FROM role_permissions").fetchone()[0]
            if count == 0:
                for role, permissions in DEFAULT_ROLE_PERMISSIONS.items():
                    conn.executemany(
                        "INSERT OR IGNORE INTO role_permissions(role,permission_code) VALUES(?,?)",
                        [(role, p) for p in permissions],
                    )
        self._optional_schema_ready = True

    def _slow_diag(self, kind: str, elapsed_ms: float, detail: str = "") -> None:
        """Write only slow DB operations to a LOCAL diagnostic file.

        Normal fast operations do zero file I/O, preserving LiteCore behavior.
        The Administration -> Collect logs button includes this file.
        """
        if elapsed_ms < 150.0:
            return
        try:
            from .config import local_logs_dir
            path = local_logs_dir() / "db_slow.log"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {kind} | {elapsed_ms:.1f} ms | {detail}\n")
        except Exception:
            pass

    def _connect(self, timeout: float = 3.0) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=timeout)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={max(250, int(timeout * 1000))}")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-12000")
        return conn

    @contextmanager
    def read_conn(self):
        started = time.perf_counter()
        conn = self._connect(2.5)
        try:
            yield conn
        finally:
            conn.close()
            self._slow_diag("READ", (time.perf_counter() - started) * 1000.0, str(self.path))

    @contextmanager
    def write_conn(self, retries: int = 6):
        started = time.perf_counter()
        last: Exception | None = None
        conn: sqlite3.Connection | None = None
        attempts_used = 0
        for attempt in range(retries):
            attempts_used = attempt + 1
            conn = self._connect(1.4)
            try:
                conn.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError as exc:
                conn.close()
                conn = None
                last = exc
                if not is_busy(exc) or attempt == retries - 1:
                    self._slow_diag("WRITE-LOCK-ERROR", (time.perf_counter() - started) * 1000.0, str(exc))
                    raise
                time.sleep(min(0.08 + 0.08 * attempt, 0.45))
        if conn is None:
            raise DatabaseError(str(last or "Не удалось открыть транзакцию"))
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
            self._slow_diag("WRITE", (time.perf_counter() - started) * 1000.0, f"attempts={attempts_used}; {self.path}")

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    @staticmethod
    def _add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        if column not in Database._columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _ensure_schema(self) -> None:
        new_db = not self.path.exists() or self.path.stat().st_size == 0
        with self.write_conn(retries=10) as conn:
            if new_db:
                # DELETE journal is the conservative mode for SMB. Set only on first creation.
                try:
                    conn.execute("PRAGMA journal_mode=DELETE")
                except Exception:
                    pass
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    access_control_enabled INTEGER NOT NULL DEFAULT 1,
                    CHECK (id = 1)
                );

                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    is_master INTEGER NOT NULL DEFAULT 0,
                    registration_date TEXT NOT NULL,
                    edit_date TEXT
                );

                CREATE TABLE IF NOT EXISTS departments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    registration_date TEXT NOT NULL,
                    edit_date TEXT
                );

                CREATE TABLE IF NOT EXISTS work_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    code TEXT NOT NULL UNIQUE,
                    price REAL NOT NULL,
                    registration_date TEXT NOT NULL,
                    edit_date TEXT,
                    is_favorite INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS work_type_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_type_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    changed_by TEXT,
                    FOREIGN KEY (work_type_id) REFERENCES work_types(id)
                );

                CREATE TABLE IF NOT EXISTS work_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_date TEXT NOT NULL,
                    shift_type TEXT NOT NULL,
                    master_id INTEGER NOT NULL,
                    department_id INTEGER NOT NULL,
                    registration_date TEXT NOT NULL,
                    version TEXT NOT NULL,
                    parent_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'saved',
                    edited_by TEXT,
                    edit_date TEXT,
                    comment TEXT,
                    separate_worker INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (master_id) REFERENCES employees(id),
                    FOREIGN KEY (department_id) REFERENCES departments(id),
                    FOREIGN KEY (parent_id) REFERENCES work_orders(id)
                );

                CREATE TABLE IF NOT EXISTS work_order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    employee_id INTEGER,
                    work_type_id INTEGER,
                    hours REAL,
                    fixed_boxes REAL,
                    fixed_weight REAL,
                    actual_value REAL,
                    work_name_snapshot TEXT,
                    work_code_snapshot TEXT,
                    price_snapshot REAL,
                    FOREIGN KEY (order_id) REFERENCES work_orders(id)
                );

                CREATE TABLE IF NOT EXISTS work_order_layout_rows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    row_index INTEGER NOT NULL,
                    employee_id INTEGER,
                    employee_name_snapshot TEXT,
                    work_type_id INTEGER,
                    work_name_snapshot TEXT,
                    work_code_snapshot TEXT,
                    price_snapshot REAL,
                    hours REAL,
                    fixed_boxes REAL,
                    fixed_weight REAL,
                    fixed_total REAL,
                    fixed_payment REAL,
                    actual_value REAL,
                    actual_payment REAL,
                    payment REAL,
                    created_at TEXT,
                    FOREIGN KEY(order_id) REFERENCES work_orders(id)
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    object_type TEXT,
                    object_name TEXT,
                    details TEXT
                );

                CREATE TABLE IF NOT EXISTS db_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS permissions (
                    code TEXT PRIMARY KEY,
                    label TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS role_permissions (
                    role TEXT NOT NULL,
                    permission_code TEXT NOT NULL,
                    PRIMARY KEY(role, permission_code),
                    FOREIGN KEY(permission_code) REFERENCES permissions(code)
                );

                CREATE TABLE IF NOT EXISTS work_order_edit_locks (
                    lock_key TEXT PRIMARY KEY,
                    order_id INTEGER,
                    username TEXT NOT NULL,
                    role TEXT,
                    computer TEXT,
                    process_id INTEGER,
                    token TEXT NOT NULL,
                    acquired_at REAL NOT NULL,
                    heartbeat_at REAL NOT NULL
                );
                """
            )

            # In-place compatibility with v2..v151 databases.
            self._add_column(conn, "users", "is_active", "INTEGER NOT NULL DEFAULT 1")
            self._add_column(conn, "work_types", "is_favorite", "INTEGER NOT NULL DEFAULT 0")
            self._add_column(conn, "work_orders", "status", "TEXT NOT NULL DEFAULT 'saved'")
            self._add_column(conn, "work_orders", "edited_by", "TEXT")
            self._add_column(conn, "work_orders", "edit_date", "TEXT")
            self._add_column(conn, "work_orders", "comment", "TEXT")
            self._add_column(conn, "work_orders", "separate_worker", "INTEGER NOT NULL DEFAULT 0")
            for col, ddl in (
                ("work_name_snapshot", "TEXT"),
                ("work_code_snapshot", "TEXT"),
                ("price_snapshot", "REAL"),
            ):
                self._add_column(conn, "work_order_items", col, ddl)
            for col, ddl in (
                ("employee_name_snapshot", "TEXT"),
                ("fixed_total", "REAL"),
                ("fixed_payment", "REAL"),
                ("actual_payment", "REAL"),
                ("payment", "REAL"),
                ("created_at", "TEXT"),
            ):
                self._add_column(conn, "work_order_layout_rows", col, ddl)

            conn.execute("INSERT OR IGNORE INTO settings(id, access_control_enabled) VALUES(1, 1)")
            conn.execute(
                "INSERT OR REPLACE INTO db_meta(key,value) VALUES('smartorder_lite_schema',?)",
                (str(SCHEMA_VERSION),),
            )

            from .security import PERMISSION_LABELS
            for code in ALL_PERMISSIONS:
                conn.execute(
                    "INSERT OR IGNORE INTO permissions(code,label) VALUES(?,?)",
                    (code, PERMISSION_LABELS.get(code, code)),
                )
            role_count = conn.execute("SELECT COUNT(*) FROM role_permissions").fetchone()[0]
            if role_count == 0:
                for role, permissions in DEFAULT_ROLE_PERMISSIONS.items():
                    conn.executemany(
                        "INSERT OR IGNORE INTO role_permissions(role,permission_code) VALUES(?,?)",
                        [(role, p) for p in permissions],
                    )

            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_orders_date ON work_orders(order_date);
                CREATE INDEX IF NOT EXISTS idx_orders_master ON work_orders(master_id);
                CREATE INDEX IF NOT EXISTS idx_orders_department ON work_orders(department_id);
                CREATE INDEX IF NOT EXISTS idx_orders_parent ON work_orders(parent_id);
                CREATE INDEX IF NOT EXISTS idx_items_order ON work_order_items(order_id);
                CREATE INDEX IF NOT EXISTS idx_layout_order ON work_order_layout_rows(order_id, row_index);
                CREATE INDEX IF NOT EXISTS idx_audit_id ON audit_log(id DESC);
                CREATE INDEX IF NOT EXISTS idx_lock_heartbeat ON work_order_edit_locks(heartbeat_at);
                """
            )

    # ---------- cache ----------
    def _cached(self, key: str, loader, ttl: float = 20.0):
        now = time.monotonic()
        with self._cache_lock:
            item = self._cache.get(key)
            if item and now - item[0] <= ttl:
                return list(item[1])
        value = list(loader())
        with self._cache_lock:
            self._cache[key] = (now, value)
        return list(value)

    def invalidate_cache(self, *prefixes: str) -> None:
        with self._cache_lock:
            if not prefixes:
                self._cache.clear()
                return
            for key in list(self._cache):
                if any(key.startswith(prefix) for prefix in prefixes):
                    self._cache.pop(key, None)

    # ---------- authentication / permissions ----------
    def startup_bundle(self) -> tuple[bool, bool]:
        """One SMB connection for startup auth state + order-filter references.

        The main window asks for masters/departments immediately.  Priming those
        caches here avoids two extra SQLite opens after login.
        """
        with self.read_conn() as conn:
            has_users = bool(conn.execute("SELECT 1 FROM users LIMIT 1").fetchone())
            row = conn.execute("SELECT access_control_enabled FROM settings WHERE id=1").fetchone()
            access_enabled = True if row is None else bool(int(row[0] or 0))
            masters = conn.execute(
                "SELECT id,name,is_master,registration_date,edit_date FROM employees WHERE is_master=1 ORDER BY name COLLATE NOCASE"
            ).fetchall()
            departments = sorted(
                conn.execute("SELECT id,name,registration_date,edit_date FROM departments").fetchall(),
                key=lambda row: department_sort_key(row[1]),
            )
        now = time.monotonic()
        with self._cache_lock:
            self._cache["employees:True"] = (now, list(masters))
            self._cache["departments"] = (now, list(departments))
        return has_users, access_enabled

    def has_users(self) -> bool:
        with self.read_conn() as conn:
            return bool(conn.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def is_access_control_enabled(self) -> bool:
        with self.read_conn() as conn:
            row = conn.execute("SELECT access_control_enabled FROM settings WHERE id=1").fetchone()
            return True if row is None else bool(int(row[0] or 0))

    def set_access_control(self, actor: SessionUser, enabled: bool) -> None:
        from .account_store import validate_actor
        validate_actor(self,actor,Permission.ACCESS_CONTROL)
        value = 1 if enabled else 0
        with self.write_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO settings(id,access_control_enabled) VALUES(1,?)", (value,))
            conn.execute("UPDATE settings SET access_control_enabled=? WHERE id=1", (value,))
            self._audit_conn(conn, actor.username, "Изменил", "Настройка", "Разрешительный режим", "Включён" if enabled else "Выключен")


    def create_first_admin(self, username: str, password: str) -> int:
        username = str(username or "").strip()
        password = str(password or "")
        if not username or len(username) > 128 or any(ord(ch) < 32 for ch in username):
            raise ValueError("Логин обязателен и должен быть не длиннее 128 символов")
        if len(password) < 8:
            raise ValueError("Пароль должен содержать не менее 8 символов.")
        if len(password) > 4096:
            raise ValueError("Пароль слишком длинный.")
        with self.write_conn() as conn:
            if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise DatabaseError("Пользователи уже существуют")
            cur = conn.execute(
                "INSERT INTO users(username,password_hash,role,is_active) VALUES(?,?,?,1)",
                (username.strip(), hash_password(password), "Администратор"),
            )
            self._audit_conn(conn, username.strip(), "Создал", "Пользователь", username.strip(), "Первый администратор")
            return int(cur.lastrowid)

    def ensure_account_schema(self):
        from .account_store import ensure_accounts
        ensure_accounts(self)

    def user_options(self, user_id):
        from .account_store import options
        return options(self, user_id)

    def permissions_for_user(self, user_id, role):
        from .account_store import effective_permissions
        return effective_permissions(self, user_id, role)

    def get_personalization(self, actor):
        from .account_store import get_personalization
        return get_personalization(self, actor)

    def save_personalization(self, actor, enabled, payload):
        from .account_store import save_personalization
        return save_personalization(self, actor, enabled, payload)

    def role_permissions(self, role: str) -> frozenset[str]:
        """Fixed permissions from the technical specification.

        Old role_permissions rows are intentionally ignored so a legacy DB
        cannot silently change the RC3 access model.
        """
        result=set()
        for name in split_roles(role):
            result.update(DEFAULT_ROLE_PERMISSIONS.get(name, set()))
        return frozenset(result)

    def authenticate(self, username: str, password: str) -> SessionUser | None:
        username = str(username or "").strip()
        password = str(password or "")
        # Avoid doing a database/hash lookup for unbounded input pasted into
        # the login form.  Existing legacy accounts remain readable.
        if not username or len(username) > 128 or len(str(password or "")) > 4096:
            return None
        from .account_store import activate_due
        activate_due(self)
        with self.read_conn() as conn:
            row = conn.execute(
                "SELECT id,username,password_hash,role,COALESCE(is_active,1) FROM users WHERE username=? COLLATE NOCASE",
                (username,),
            ).fetchone()
            # Compatibility with old aliases for the single admin account.
            if row is None and username.lower() in {"админ", "admin", "flvby"}:
                row = conn.execute(
                    "SELECT id,username,password_hash,role,COALESCE(is_active,1) FROM users WHERE role='Администратор' ORDER BY id LIMIT 1"
                ).fetchone()
        if row is None or not int(row[4]):
            return None
        valid, upgrade = verify_password(password, str(row[2]))
        if not valid:
            return None
        if upgrade:
            try:
                with self.write_conn() as conn:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), int(row[0])))
            except Exception:
                pass
        role=";".join(split_roles(row[3]))
        if role!=str(row[3]):
            with self.write_conn() as conn:conn.execute("UPDATE users SET role=? WHERE id=?",(role,int(row[0])))
        return SessionUser(int(row[0]),str(row[1]),role,self.permissions_for_user(int(row[0]),role))

    def list_users(self) -> list[sqlite3.Row]:
        from .account_store import activate_due
        activate_due(self)
        with self.read_conn() as conn:
            return conn.execute("SELECT u.id,u.username,u.role,COALESCE(u.is_active,1) AS is_active,o.activate_at,o.permissions_json FROM users u LEFT JOIN account_options o ON o.user_id=u.id ORDER BY u.username COLLATE NOCASE").fetchall()

    def add_user(self, actor: SessionUser, username: str, password: str, role: str, *, permissions=None, activate_at=None) -> None:
        from .account_store import validate_actor, normalized_permissions, activation_value
        current=validate_actor(self,actor,Permission.USERS_MANAGE)
        username=str(username or "").strip();password=str(password or "")
        names=split_roles(role);role=";".join(names)
        if not username or len(username)>128 or any(ord(ch)<32 for ch in username):
            raise ValueError("Логин обязателен и должен быть не длиннее 128 символов")
        if len(password)<8:raise ValueError("Пароль должен содержать не менее 8 символов.")
        if len(password)>4096:raise ValueError("Пароль слишком длинный.")
        if not names or any(name not in DEFAULT_ROLE_PERMISSIONS for name in names):raise ValueError("Неизвестная роль пользователя")
        chosen=normalized_permissions(permissions);activation=activation_value(activate_at)
        requested=self.role_permissions(role) if chosen is None else set(chosen)
        if Permission.PERMISSIONS_MANAGE not in current and (chosen is not None or not set(requested)<=set(current)):
            raise DatabaseError("Нет прав на назначение этих разрешений")
        encoded=hash_password(password)
        with self.write_conn() as conn:
            current=validate_actor(self,actor,Permission.USERS_MANAGE,conn)
            if Permission.PERMISSIONS_MANAGE not in current and (chosen is not None or not set(requested)<=set(current)):raise DatabaseError("Нет прав на назначение этих разрешений")
            cur=conn.execute("INSERT INTO users(username,password_hash,role,is_active) VALUES(?,?,?,?)",(username,encoded,role,0 if activation else 1))
            conn.execute("INSERT INTO account_options(user_id,permissions_json,activate_at) VALUES(?,?,?)",(cur.lastrowid,json.dumps(chosen) if chosen is not None else None,activation))
            self._audit_conn(conn,actor.username,"Добавил","Пользователь",username,f"Роль: {role}; активация: {activation or 'сразу'}; индивидуальные права: {chosen is not None}")

    def update_user(self, actor: SessionUser, user_id: int, username: str, role: str, password: str = "", *, permissions=UNSET, activate_at=UNSET) -> None:
        from .account_store import validate_actor, normalized_permissions, activation_value, guard_last_admin,require_manage_target
        current=validate_actor(self,actor,Permission.USERS_MANAGE)
        username=str(username or "").strip();password=str(password or "");names=split_roles(role);role=";".join(names)
        if not username or len(username)>128 or any(ord(ch)<32 for ch in username):raise ValueError("Логин обязателен и должен быть не длиннее 128 символов")
        if not names or any(name not in DEFAULT_ROLE_PERMISSIONS for name in names):raise ValueError("Неизвестная роль пользователя")
        if password and len(password)<8:raise ValueError("Пароль должен содержать не менее 8 символов.")
        if len(password)>4096:raise ValueError("Пароль слишком длинный.")
        chosen=UNSET if permissions is UNSET else normalized_permissions(permissions)
        activation=UNSET if activate_at is UNSET else activation_value(activate_at)
        encoded=hash_password(password) if password else None
        with self.write_conn() as conn:
            current=validate_actor(self,actor,Permission.USERS_MANAGE,conn);require_manage_target(self,conn,current,user_id)
            old=conn.execute("SELECT role,is_active FROM users WHERE id=?",(user_id,)).fetchone()
            if old is None:raise DatabaseError("Пользователь не найден")
            prior=conn.execute("SELECT permissions_json,activate_at FROM account_options WHERE user_id=?",(user_id,)).fetchone()
            if Permission.PERMISSIONS_MANAGE not in current and (chosen is not UNSET or split_roles(old[0])!=names):
                raise DatabaseError("Нет прав на изменение разрешений пользователя")
            if chosen is UNSET:chosen=json.loads(prior[0]) if prior and prior[0] is not None else None
            if activation is UNSET:activation=prior[1] if prior else None
            active=0 if activation else (1 if activate_at is not UNSET and prior and prior[1] else int(old[1]))
            guard_last_admin(self,conn,user_id,role,active,chosen)
            conn.execute("UPDATE users SET username=?,role=?,is_active=? WHERE id=?",(username,role,active,user_id))
            if encoded:conn.execute("UPDATE users SET password_hash=? WHERE id=?",(encoded,user_id))
            conn.execute("INSERT INTO account_options(user_id,permissions_json,activate_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET permissions_json=excluded.permissions_json,activate_at=excluded.activate_at",(user_id,json.dumps(chosen) if chosen is not None else None,activation))
            self._audit_conn(conn,actor.username,"Изменил","Пользователь",username,f"Роль: {role}; активация: {activation or 'не задана'}; индивидуальные права: {chosen is not None}")

    def set_user_active(self, actor: SessionUser, user_id: int, active: bool) -> None:
        from .account_store import validate_actor, guard_last_admin,require_manage_target
        validate_actor(self,actor,Permission.USERS_MANAGE)
        with self.write_conn() as conn:
            current=validate_actor(self,actor,Permission.USERS_MANAGE,conn);require_manage_target(self,conn,current,user_id)
            row=conn.execute("SELECT username,role FROM users WHERE id=?",(user_id,)).fetchone()
            if not row:return
            option=conn.execute("SELECT permissions_json FROM account_options WHERE user_id=?",(user_id,)).fetchone()
            chosen=json.loads(option[0]) if option and option[0] is not None else None
            guard_last_admin(self,conn,user_id,row[1],active,chosen)
            conn.execute("UPDATE users SET is_active=? WHERE id=?",(int(bool(active)),user_id))
            conn.execute("UPDATE account_options SET activate_at=NULL WHERE user_id=?",(user_id,))
            self._audit_conn(conn,actor.username,"Включил" if active else "Отключил","Пользователь",str(row[0]),"")

    def delete_user(self, actor: SessionUser, user_id: int) -> None:
        """Delete a user while protecting the current and last admin accounts."""
        from .account_store import validate_actor,require_manage_target
        validate_actor(self,actor,Permission.USERS_MANAGE)
        user_id = int(user_id)
        if int(actor.id) == user_id:
            raise DatabaseError("Нельзя удалить текущего пользователя")
        with self.write_conn() as conn:
            current=validate_actor(self,actor,Permission.USERS_MANAGE,conn);require_manage_target(self,conn,current,user_id)
            row = conn.execute("SELECT username,role,COALESCE(is_active,1) FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                return
            username, role = str(row[0]), str(row[1])
            if "Администратор" in split_roles(role):
                count = sum(
                    1 for candidate in conn.execute("SELECT role FROM users WHERE id<>?", (user_id,)).fetchall()
                    if "Администратор" in split_roles(candidate[0])
                )
                if count == 0:
                    raise DatabaseError("Нельзя удалить последнего администратора")
            conn.execute("DELETE FROM account_options WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM user_personalization WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))
            self._audit_conn(conn, actor.username, "Удалил", "Пользователь", username, f"Роль: {role}")

    def set_role_permissions(self, actor: SessionUser, role: str, permissions: Iterable[str]) -> None:
        # RC3 uses fixed permissions from the technical specification.
        # Keep the method only as a compatibility guard for old callers; it
        # intentionally performs no schema writes.
        raise DatabaseError("Права ролей заданы техническим заданием и не изменяются вручную")

    # ---------- soft-delete markers for historical references ----------
    @staticmethod
    def _ensure_soft_delete_schema_conn(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS soft_deleted_entities (
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                marked_at TEXT NOT NULL,
                marked_by TEXT,
                PRIMARY KEY(entity_type, entity_id)
            )
            """
        )

    def _soft_deleted_entries(self, entity_type: str) -> set[int]:
        key = f"soft_deleted:{entity_type}"
        def loader():
            try:
                with self.read_conn() as conn:
                    rows = conn.execute(
                        "SELECT entity_id FROM soft_deleted_entities WHERE entity_type=?",
                        (str(entity_type),),
                    ).fetchall()
                    return [int(row[0]) for row in rows]
            except sqlite3.OperationalError as exc:
                # Existing v151/LiteCore databases do not have this RC16 service
                # table until the first historical record is marked for deletion.
                if "no such table" in str(exc).lower():
                    return []
                raise
        return set(self._cached(key, loader, ttl=20.0))

    def is_soft_deleted(self, entity_type: str, entity_id: int) -> bool:
        return int(entity_id) in self._soft_deleted_entries(entity_type)

    def _mark_soft_deleted_conn(self, conn: sqlite3.Connection, entity_type: str, entity_id: int, actor: SessionUser) -> None:
        self._ensure_soft_delete_schema_conn(conn)
        conn.execute(
            "INSERT OR REPLACE INTO soft_deleted_entities(entity_type,entity_id,marked_at,marked_by) VALUES(?,?,?,?)",
            (str(entity_type), int(entity_id), now_text(), actor.username),
        )

    def get_active_employees(self, is_master: bool | None = None) -> list[sqlite3.Row]:
        marked = self._soft_deleted_entries("employee")
        return [row for row in self.get_employees(is_master) if int(row[0]) not in marked]

    def get_active_work_types(self) -> list[sqlite3.Row]:
        marked = self._soft_deleted_entries("work_type")
        return [row for row in self.get_work_types() if int(row[0]) not in marked]

    def get_active_departments(self) -> list[sqlite3.Row]:
        marked = self._soft_deleted_entries("department")
        return [row for row in self.get_departments() if int(row[0]) not in marked]

    def list_recent_deleted_employees(self, is_master: bool, days: int = RECENT_DELETED_DAYS) -> list[sqlite3.Row]:
        """People soft-deleted during the visible recycle-bin window."""
        cutoff = (datetime.now() - timedelta(days=max(1, int(days)))).strftime(DT_FMT)
        try:
            with self.read_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT e.id,e.name,e.is_master,e.registration_date,e.edit_date,s.marked_at,s.marked_by
                    FROM employees e
                    JOIN soft_deleted_entities s ON s.entity_type='employee' AND s.entity_id=e.id
                    WHERE e.is_master=?
                    ORDER BY s.marked_at DESC,e.name COLLATE NOCASE
                    """,
                    (1 if is_master else 0,),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise
        threshold = datetime.strptime(cutoff, DT_FMT)
        result = []
        for row in rows:
            try:
                marked_at = datetime.strptime(str(row[5]), DT_FMT)
            except Exception:
                continue
            if marked_at >= threshold:
                result.append(row)
        return result

    def list_recent_deleted_departments(self, days: int = RECENT_DELETED_DAYS) -> list[sqlite3.Row]:
        cutoff = datetime.now() - timedelta(days=max(1, int(days)))
        try:
            with self.read_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT d.id,d.name,d.registration_date,d.edit_date,s.marked_at,s.marked_by
                    FROM departments d
                    JOIN soft_deleted_entities s ON s.entity_type='department' AND s.entity_id=d.id
                    ORDER BY s.marked_at DESC
                    """
                ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise
        result = []
        for row in rows:
            try:
                marked_at = datetime.strptime(str(row[4]), DT_FMT)
            except Exception:
                continue
            if marked_at >= cutoff:
                result.append(row)
        return sorted(result, key=lambda row: department_sort_key(row[1]))

    def run_retention_maintenance(self, force: bool = False) -> dict[str, int | bool]:
        """Daily retention cleanup.

        - Entire order families are retained for 365 days from their first
          registration and then removed with their detail/layout rows.
        - People/departments marked for deletion disappear from the UI after
          30 days immediately (query-side). Their underlying rows are physically
          removed only after no retained order references them.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        order_cutoff = (datetime.now() - timedelta(days=ORDER_RETENTION_DAYS)).strftime("%Y-%m-%d")
        recent_cutoff = datetime.now() - timedelta(days=RECENT_DELETED_DAYS)
        stats: dict[str, int | bool] = {
            "skipped": False, "order_families": 0, "orders": 0,
            "employees": 0, "departments": 0,
        }
        # On normal launches most clients only perform this tiny read. Avoid
        # acquiring the shared SMB write lock when another client already ran
        # today's maintenance. The write transaction below re-checks for races.
        if not force:
            try:
                with self.read_conn() as check_conn:
                    last = check_conn.execute("SELECT value FROM db_meta WHERE key='retention_last_run'").fetchone()
                if last and str(last[0]) == today:
                    stats["skipped"] = True
                    return stats
            except Exception:
                pass
        with self.write_conn(retries=8) as conn:
            self._ensure_soft_delete_schema_conn(conn)
            last = conn.execute("SELECT value FROM db_meta WHERE key='retention_last_run'").fetchone()
            if not force and last and str(last[0]) == today:
                stats["skipped"] = True
                return stats

            base_expr = "CASE WHEN instr(version,'.')>0 THEN substr(version,1,instr(version,'.')-1) ELSE version END"
            date_expr = "substr(registration_date,7,4)||'-'||substr(registration_date,4,2)||'-'||substr(registration_date,1,2)"
            bases = [str(r[0]) for r in conn.execute(
                f"SELECT {base_expr} AS base FROM work_orders GROUP BY base HAVING MIN({date_expr})<=?",
                (order_cutoff,),
            ).fetchall()]
            removed_orders = 0
            for base in bases:
                rows = conn.execute(
                    f"SELECT id FROM work_orders WHERE {base_expr}=?", (base,)
                ).fetchall()
                ids = [int(r[0]) for r in rows]
                if not ids:
                    continue
                q = ','.join('?' for _ in ids)
                try:
                    conn.execute(f"DELETE FROM work_order_edit_locks WHERE order_id IN ({q})", ids)
                except sqlite3.OperationalError:
                    pass
                conn.execute(f"DELETE FROM work_order_items WHERE order_id IN ({q})", ids)
                try:
                    conn.execute(f"DELETE FROM work_order_layout_rows WHERE order_id IN ({q})", ids)
                except sqlite3.OperationalError:
                    pass
                # Break self-references before deleting the whole version family.
                conn.execute(f"UPDATE work_orders SET parent_id=NULL WHERE id IN ({q})", ids)
                conn.execute(f"DELETE FROM work_orders WHERE id IN ({q})", ids)
                removed_orders += len(ids)

            stats["order_families"] = len(bases)
            stats["orders"] = removed_orders

            # Purge old tombstones only when no retained order still needs them.
            markers = conn.execute(
                "SELECT entity_type,entity_id,marked_at FROM soft_deleted_entities WHERE entity_type IN ('employee','department')"
            ).fetchall()
            for marker in markers:
                entity_type, entity_id = str(marker[0]), int(marker[1])
                try:
                    marked_at = datetime.strptime(str(marker[2]), DT_FMT)
                except Exception:
                    continue
                if marked_at > recent_cutoff:
                    continue
                if entity_type == "employee":
                    master_refs = int(conn.execute("SELECT COUNT(*) FROM work_orders WHERE master_id=?", (entity_id,)).fetchone()[0] or 0)
                    item_refs = int(conn.execute("SELECT COUNT(*) FROM work_order_items WHERE employee_id=?", (entity_id,)).fetchone()[0] or 0)
                    try:
                        layout_refs = int(conn.execute("SELECT COUNT(*) FROM work_order_layout_rows WHERE employee_id=?", (entity_id,)).fetchone()[0] or 0)
                    except sqlite3.OperationalError:
                        layout_refs = 0
                    if master_refs + item_refs + layout_refs == 0:
                        conn.execute("DELETE FROM employees WHERE id=?", (entity_id,))
                        conn.execute("DELETE FROM soft_deleted_entities WHERE entity_type='employee' AND entity_id=?", (entity_id,))
                        stats["employees"] = int(stats["employees"]) + 1
                elif entity_type == "department":
                    refs = int(conn.execute("SELECT COUNT(*) FROM work_orders WHERE department_id=?", (entity_id,)).fetchone()[0] or 0)
                    if refs == 0:
                        conn.execute("DELETE FROM departments WHERE id=?", (entity_id,))
                        conn.execute("DELETE FROM soft_deleted_entities WHERE entity_type='department' AND entity_id=?", (entity_id,))
                        stats["departments"] = int(stats["departments"]) + 1

            conn.execute(
                "INSERT INTO db_meta(key,value) VALUES('retention_last_run',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (today,),
            )
            if removed_orders:
                self._audit_conn(
                    conn, "Система", "Удалил по сроку хранения", "Наряды",
                    f"Семейств: {len(bases)}", f"Версий удалено: {removed_orders}; срок: {ORDER_RETENTION_DAYS} дней",
                )
        self.invalidate_cache("employees", "departments", "soft_deleted")
        return stats

    # ---------- references ----------
    def _ensure_reference_authors(self):
        if getattr(self, "_reference_authors_ready", False):
            return
        with self.write_conn() as conn:
            for table in ("employees", "departments", "work_types"):
                self._add_column(conn, table, "created_by", "TEXT")
                self._add_column(conn, table, "updated_by", "TEXT")
        self._reference_authors_ready = True

    def reference_audit(self, kind):
        tables = {"employee": "employees", "department": "departments", "work_type": "work_types"}
        table = tables[kind]
        def load():
            with self.read_conn() as conn:
                columns = self._columns(conn, table)
                created = "created_by" if "created_by" in columns else "''"
                updated = "updated_by" if "updated_by" in columns else "''"
                return conn.execute(f"SELECT id,{created},{updated} FROM {table}").fetchall()
        return {int(row[0]): (str(row[1] or ""), str(row[2] or ""))
                for row in self._cached(table + ":authors", load)}

    def get_employees(self, is_master: bool | None = None) -> list[sqlite3.Row]:
        key = f"employees:{is_master}"
        def loader():
            with self.read_conn() as conn:
                if is_master is None:
                    return conn.execute(
                        "SELECT id,name,is_master,registration_date,edit_date FROM employees ORDER BY name COLLATE NOCASE"
                    ).fetchall()
                return conn.execute(
                    "SELECT id,name,is_master,registration_date,edit_date FROM employees WHERE is_master=? ORDER BY name COLLATE NOCASE",
                    (1 if is_master else 0,),
                ).fetchall()
        return self._cached(key, loader)

    def add_employee(self, actor: SessionUser, name: str, is_master: bool = False) -> int:
        self._ensure_reference_authors()
        name = name.strip()
        with self.write_conn() as conn:
            cur = conn.execute(
                "INSERT INTO employees(name,is_master,registration_date,created_by) VALUES(?,?,?,?)",
                (name, 1 if is_master else 0, now_text(), actor.username),
            )
            self._audit_conn(conn, actor.username, "Добавил", "Мастер" if is_master else "Сотрудник", name, "")
        self.invalidate_cache("employees")
        return int(cur.lastrowid)

    def update_employee(self, actor: SessionUser, employee_id: int, name: str) -> None:
        self._ensure_reference_authors()
        name = name.strip()
        with self.write_conn() as conn:
            conn.execute("UPDATE employees SET name=?,edit_date=?,updated_by=? WHERE id=?", (name, now_text(), actor.username, employee_id))
            self._audit_conn(conn, actor.username, "Изменил", "Сотрудник", name, f"id={employee_id}")
        self.invalidate_cache("employees")

    def delete_employee(self, actor: SessionUser, employee_id: int) -> str:
        """Delete unused people; historical references become an inactive soft-delete marker."""
        employee_id = int(employee_id)
        with self.write_conn() as conn:
            row = conn.execute("SELECT name,is_master FROM employees WHERE id=?", (employee_id,)).fetchone()
            if not row:
                raise DatabaseError("Сотрудник не найден.")
            name, is_master = str(row[0]), bool(row[1])
            # A person may be referenced as the order master, as a work-line employee,
            # or only in the persisted visual layout (employee without a work).
            master_count = int(conn.execute("SELECT COUNT(*) FROM work_orders WHERE master_id=?", (employee_id,)).fetchone()[0] or 0)
            item_count = int(conn.execute("SELECT COUNT(*) FROM work_order_items WHERE employee_id=?", (employee_id,)).fetchone()[0] or 0)
            try:
                layout_count = int(conn.execute("SELECT COUNT(*) FROM work_order_layout_rows WHERE employee_id=?", (employee_id,)).fetchone()[0] or 0)
            except sqlite3.OperationalError:
                layout_count = 0
            used = master_count + item_count + layout_count
            if used:
                self._mark_soft_deleted_conn(conn, "employee", employee_id, actor)
                kind = "Мастер" if is_master else "Сотрудник"
                self._audit_conn(conn, actor.username, "Пометил на удаление", kind, name, f"Связанных записей: {used}")
                result = "marked"
            else:
                # Remove a stale marker if an administrator is deleting an entity that
                # became unused after DB maintenance.
                try:
                    conn.execute("DELETE FROM soft_deleted_entities WHERE entity_type='employee' AND entity_id=?", (employee_id,))
                except sqlite3.OperationalError:
                    pass
                conn.execute("DELETE FROM employees WHERE id=?", (employee_id,))
                self._audit_conn(conn, actor.username, "Удалил", "Мастер" if is_master else "Сотрудник", name, "")
                result = "deleted"
        self.invalidate_cache("employees", "soft_deleted")
        return result

    def get_departments(self) -> list[sqlite3.Row]:
        def loader():
            with self.read_conn() as conn:
                return sorted(
                    conn.execute("SELECT id,name,registration_date,edit_date FROM departments").fetchall(),
                    key=lambda row: department_sort_key(row[1]),
                )
        return self._cached("departments", loader)

    def add_department(self, actor: SessionUser, name: str) -> int:
        self._ensure_reference_authors()
        with self.write_conn() as conn:
            cur = conn.execute(
                "INSERT INTO departments(name,registration_date,created_by) VALUES(?,?,?)", (name.strip(), now_text(), actor.username)
            )
            self._audit_conn(conn, actor.username, "Добавил", "Подразделение", name.strip(), "")
        self.invalidate_cache("departments")
        return int(cur.lastrowid)

    def update_department(self, actor: SessionUser, department_id: int, name: str) -> None:
        self._ensure_reference_authors()
        with self.write_conn() as conn:
            conn.execute("UPDATE departments SET name=?,edit_date=?,updated_by=? WHERE id=?", (name.strip(), now_text(), actor.username, department_id))
            self._audit_conn(conn, actor.username, "Изменил", "Подразделение", name.strip(), f"id={department_id}")
        self.invalidate_cache("departments")

    def delete_department(self, actor: SessionUser, department_id: int) -> str:
        department_id = int(department_id)
        with self.write_conn() as conn:
            row = conn.execute("SELECT name FROM departments WHERE id=?", (department_id,)).fetchone()
            if not row:
                raise DatabaseError("Подразделение не найдено.")
            name = str(row[0])
            used = int(conn.execute("SELECT COUNT(*) FROM work_orders WHERE department_id=?", (department_id,)).fetchone()[0] or 0)
            if used:
                self._mark_soft_deleted_conn(conn, "department", department_id, actor)
                self._audit_conn(conn, actor.username, "Пометил на удаление", "Подразделение", name, f"Связанных нарядов: {used}")
                result = "marked"
            else:
                try:
                    conn.execute("DELETE FROM soft_deleted_entities WHERE entity_type='department' AND entity_id=?", (department_id,))
                except sqlite3.OperationalError:
                    pass
                conn.execute("DELETE FROM departments WHERE id=?", (department_id,))
                self._audit_conn(conn, actor.username, "Удалил", "Подразделение", name, "")
                result = "deleted"
        self.invalidate_cache("departments", "soft_deleted")
        return result

    def get_work_types(self) -> list[sqlite3.Row]:
        def loader():
            with self.read_conn() as conn:
                return conn.execute(
                    "SELECT id,name,code,price,registration_date,edit_date,COALESCE(is_favorite,0) FROM work_types ORDER BY name COLLATE NOCASE"
                ).fetchall()
        return self._cached("work_types", loader)

    def set_work_fact_unit(self, actor: SessionUser, work_id: int, unit: str) -> None:
        if unit not in ("h", "kg", "pcs", "unknown"):
            raise ValueError("Неизвестная единица ФАКТ")
        with self.write_conn() as conn:
            if not conn.execute("SELECT 1 FROM work_types WHERE id=?", (work_id,)).fetchone():
                raise DatabaseError("Работа не найдена")
            conn.execute("INSERT INTO db_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("rc20_fact_unit_" + str(int(work_id)), unit))
            self._audit_conn(conn, actor.username, "Изменена единица ФАКТ", "work_type", str(work_id), "Единица: " + unit)

    def add_work_type(self, actor: SessionUser, name: str, code: str, price) -> int:
        self._ensure_reference_authors()
        name = str(name or "").strip()
        code = str(code or "").strip()
        price_value = float(str(price).replace(",", "."))
        if not name or not code:
            raise ValueError("Заполните наименование и код работы")
        stamp = now_text()
        with self.write_conn() as conn:
            same_name = conn.execute("SELECT 1 FROM work_types WHERE name=? COLLATE NOCASE LIMIT 1", (name,)).fetchone()
            if same_name:
                raise DatabaseError(f"Работа «{name}» уже существует")
            same_code = conn.execute("SELECT 1 FROM work_types WHERE code=? COLLATE NOCASE LIMIT 1", (code,)).fetchone()
            if same_code:
                raise DatabaseError(f"Код работы «{code}» уже используется")
            cur = conn.execute(
                "INSERT INTO work_types(name,code,price,registration_date,is_favorite,created_by) VALUES(?,?,?,?,0,?)",
                (name, code, price_value, stamp, actor.username),
            )
            work_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO work_type_prices(work_type_id,price,valid_from,changed_by) VALUES(?,?,?,?)",
                (work_id, price_value, stamp, actor.username),
            )
            self._audit_conn(conn, actor.username, "Добавил", "Номенклатура", name, f"{code} = {price_value}")
        self.invalidate_cache("work_types")
        return work_id

    def update_work_type(self, actor: SessionUser, work_id: int, name: str, code: str, price) -> None:
        self._ensure_reference_authors()
        name = str(name or "").strip()
        code = str(code or "").strip()
        price_value = float(dec(price) or 0)
        if not name or not code:
            raise ValueError("Заполните наименование и код работы")
        stamp = now_text()
        with self.write_conn() as conn:
            same_name = conn.execute("SELECT 1 FROM work_types WHERE id<>? AND name=? COLLATE NOCASE LIMIT 1", (work_id, name)).fetchone()
            if same_name:
                raise DatabaseError(f"Работа «{name}» уже существует")
            same_code = conn.execute("SELECT 1 FROM work_types WHERE id<>? AND code=? COLLATE NOCASE LIMIT 1", (work_id, code)).fetchone()
            if same_code:
                raise DatabaseError(f"Код работы «{code}» уже используется")
            old = conn.execute("SELECT price FROM work_types WHERE id=?", (work_id,)).fetchone()
            conn.execute(
                "UPDATE work_types SET name=?,code=?,price=?,edit_date=?,updated_by=? WHERE id=?",
                (name, code, price_value, stamp, actor.username, work_id),
            )
            if old is None or float(old[0]) != price_value:
                conn.execute(
                    "UPDATE work_type_prices SET valid_to=? WHERE work_type_id=? AND valid_to IS NULL",
                    (stamp, work_id),
                )
                conn.execute(
                    "INSERT INTO work_type_prices(work_type_id,price,valid_from,changed_by) VALUES(?,?,?,?)",
                    (work_id, price_value, stamp, actor.username),
                )
            self._audit_conn(conn, actor.username, "Изменил", "Номенклатура", name.strip(), f"{code.strip()} = {price_value}")
        self.invalidate_cache("work_types")

    def delete_work_type(self, actor: SessionUser, work_id: int) -> str:
        """Delete unused catalog entries; keep used entries as inactive historical references."""
        work_id = int(work_id)
        with self.write_conn() as conn:
            row = conn.execute("SELECT name FROM work_types WHERE id=?", (work_id,)).fetchone()
            if not row:
                raise DatabaseError("Работа не найдена или уже удалена.")
            name = str(row[0] or work_id)
            item_count = int(conn.execute("SELECT COUNT(*) FROM work_order_items WHERE work_type_id=?", (work_id,)).fetchone()[0] or 0)
            try:
                layout_count = int(conn.execute("SELECT COUNT(*) FROM work_order_layout_rows WHERE work_type_id=?", (work_id,)).fetchone()[0] or 0)
            except sqlite3.OperationalError:
                layout_count = 0
            used = item_count + layout_count
            if used:
                self._mark_soft_deleted_conn(conn, "work_type", work_id, actor)
                self._audit_conn(conn, actor.username, "Пометил на удаление", "Номенклатура", name, f"Связанных записей: {used}")
                result = "marked"
            else:
                conn.execute("DELETE FROM work_type_prices WHERE work_type_id=?", (work_id,))
                try:
                    conn.execute("DELETE FROM soft_deleted_entities WHERE entity_type='work_type' AND entity_id=?", (work_id,))
                except sqlite3.OperationalError:
                    pass
                conn.execute("DELETE FROM work_types WHERE id=?", (work_id,))
                self._audit_conn(conn, actor.username, "Удалил", "Номенклатура", name, "")
                result = "deleted"
        self.invalidate_cache("work_types", "soft_deleted")
        return result

    def import_work_types(self, actor: SessionUser, rows: Iterable[tuple[str, str, float]]) -> tuple[int, int]:
        self._ensure_reference_authors()
        stamp = now_text()
        added = dup = 0
        with self.write_conn() as conn:
            for name, code, price in rows:
                try:
                    cur = conn.execute(
                        "INSERT INTO work_types(name,code,price,registration_date,created_by) VALUES(?,?,?,?,?)",
                        (name.strip(), code.strip(), float(price), stamp, actor.username),
                    )
                    conn.execute(
                        "INSERT INTO work_type_prices(work_type_id,price,valid_from,changed_by) VALUES(?,?,?,?)",
                        (int(cur.lastrowid), float(price), stamp, actor.username),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    dup += 1
            self._audit_conn(conn, actor.username, "Импортировал", "Номенклатура", f"{added} строк", f"Дубликаты: {dup}")
        self.invalidate_cache("work_types")
        return added, dup

    def import_people(self, actor: SessionUser, names: Iterable[str], is_master: bool) -> tuple[int, int]:
        self._ensure_reference_authors()
        stamp = now_text()
        existing = {str(r[1]).strip().casefold() for r in self.get_employees(is_master)}
        added = dup = 0
        with self.write_conn() as conn:
            for name in names:
                name = name.strip()
                if not name:
                    continue
                if name.casefold() in existing:
                    dup += 1
                    continue
                conn.execute(
                    "INSERT INTO employees(name,is_master,registration_date,created_by) VALUES(?,?,?,?)",
                    (name, 1 if is_master else 0, stamp, actor.username),
                )
                existing.add(name.casefold())
                added += 1
            self._audit_conn(conn, actor.username, "Импортировал", "Мастера" if is_master else "Сотрудники", f"{added} строк", f"Дубликаты: {dup}")
        self.invalidate_cache("employees")
        return added, dup

    def import_departments(self, actor: SessionUser, names: Iterable[str]) -> tuple[int, int]:
        self._ensure_reference_authors()
        stamp = now_text()
        added = dup = 0
        cleaned = [str(n or "").strip() for n in names if str(n or "").strip()]
        with self.write_conn() as conn:
            existing = {str(r[0]).casefold().replace("ё","е") for r in conn.execute("SELECT name FROM departments").fetchall()}
            for name in cleaned:
                key = name.casefold().replace("ё","е")
                if key in existing:
                    dup += 1
                    continue
                conn.execute("INSERT INTO departments(name,registration_date,created_by) VALUES(?,?,?)", (name, stamp, actor.username))
                existing.add(key); added += 1
            if added:
                self._audit_conn(conn, actor.username, "Импортировал", "Подразделения", f"Добавлено: {added}", f"Дубликаты: {dup}")
        self.invalidate_cache("departments")
        return added, dup

    def next_order_number_preview(self) -> str:
        """Best-effort preview only; the final number is allocated atomically on save."""
        with self.read_conn() as conn:
            rows = conn.execute("SELECT version FROM work_orders WHERE instr(version,'.')=0").fetchall()
        max_base = max([int(r[0]) for r in rows if str(r[0]).isdigit()] or [0])
        return str(max_base + 1)

    # ---------- orders ----------
    @staticmethod
    def _base_version(version: str) -> str:
        return str(version).split(".", 1)[0]

    @staticmethod
    def _revision(version: str) -> int:
        text = str(version)
        if "." not in text:
            return 0
        try:
            return int(text.split(".", 1)[1])
        except Exception:
            return 0

    def list_orders(
        self,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        master_id: int | None = None,
        department_id: int | None = None,
        shift: str | None = None,
        text: str = "",
        limit: int | None = 1000,
    ) -> list[sqlite3.Row]:
        query = """
            SELECT wo.id,wo.version,wo.order_date,wo.shift_type,
                   e.name AS master,d.name AS department,wo.registration_date,
                   wo.parent_id,wo.edited_by,wo.comment
            FROM work_orders wo
            LEFT JOIN employees e ON e.id=wo.master_id
            LEFT JOIN departments d ON d.id=wo.department_id
            WHERE COALESCE(wo.status,'saved')='saved'
        """
        params: list = []
        if date:
            query += " AND wo.order_date=?"; params.append(date)
        elif date_from or date_to:
            # Stored format is dd-MM-yyyy, therefore compare normalized ISO parts.
            iso_expr = "substr(wo.order_date,7,4)||'-'||substr(wo.order_date,4,2)||'-'||substr(wo.order_date,1,2)"
            if date_from:
                query += f" AND {iso_expr}>=?"; params.append(date_from)
            if date_to:
                query += f" AND {iso_expr}<=?"; params.append(date_to)
        if master_id is not None:
            query += " AND wo.master_id=?"; params.append(master_id)
        if department_id is not None:
            query += " AND wo.department_id=?"; params.append(department_id)
        if shift:
            query += " AND wo.shift_type=?"; params.append(shift)
        if text.strip():
            like = f"%{text.strip()}%"
            query += " AND (wo.version LIKE ? OR e.name LIKE ? OR d.name LIKE ? OR COALESCE(wo.comment,'') LIKE ?)"
            params.extend([like, like, like, like])
        query += " ORDER BY CAST(wo.version AS INTEGER) DESC, wo.registration_date DESC, wo.id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(max(1, min(int(limit), 5000)))
        with self.read_conn() as conn:
            return conn.execute(query, params).fetchall()

    def _latest_for_base_conn(self, conn: sqlite3.Connection, base: str) -> sqlite3.Row | None:
        rows = conn.execute(
            "SELECT id,version FROM work_orders WHERE version=? OR version LIKE ?",
            (base, f"{base}.%"),
        ).fetchall()
        if not rows:
            return None
        return max(rows, key=lambda r: self._revision(str(r[1])))

    def order_history(self, order_id: int) -> list[dict]:
        """Return versions of one order family without holding a persistent connection."""
        with self.read_conn() as conn:
            row = conn.execute("SELECT version FROM work_orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                return []
            base = self._base_version(str(row[0]))
            rows = conn.execute(
                """
                SELECT id, version, COALESCE(edited_by,''), COALESCE(edit_date,''),
                       COALESCE(registration_date,'')
                FROM work_orders
                WHERE version=? OR version LIKE ?
                ORDER BY id DESC
                """,
                (base, f"{base}.%"),
            ).fetchall()
        result=[]
        for r in sorted(rows, key=lambda x: self._revision(str(x[1])), reverse=True):
            result.append({
                "id": int(r[0]), "version": str(r[1]), "edited_by": str(r[2] or ""),
                "edit_date": str(r[3] or ""), "registration_date": str(r[4] or ""),
            })
        return result

    def is_latest_order(self, order_id: int) -> bool:
        with self.read_conn() as conn:
            row = conn.execute("SELECT version FROM work_orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                return False
            latest = self._latest_for_base_conn(conn, self._base_version(str(row[0])))
            return bool(latest and int(latest[0]) == int(order_id))

    def get_order(self, order_id: int) -> dict | None:
        with self.read_conn() as conn:
            order_cols = self._columns(conn, "work_orders")
            separate_worker_sql = "COALESCE(wo.separate_worker,0) AS separate_worker" if "separate_worker" in order_cols else "0 AS separate_worker"
            info = conn.execute(
                f"""
                SELECT wo.id,wo.order_date,wo.shift_type,wo.master_id,e.name AS master,
                       wo.department_id,d.name AS department,wo.registration_date,wo.version,
                       wo.parent_id,wo.edited_by,wo.edit_date,COALESCE(wo.comment,'') AS comment,
                       {separate_worker_sql}
                FROM work_orders wo
                LEFT JOIN employees e ON e.id=wo.master_id
                LEFT JOIN departments d ON d.id=wo.department_id
                WHERE wo.id=?
                """, (order_id,),
            ).fetchone()
            if not info:
                return None
            layout_cols = self._columns(conn, "work_order_layout_rows")
            fixed_payment_sql = "fixed_payment" if "fixed_payment" in layout_cols else "NULL AS fixed_payment"
            actual_payment_sql = "actual_payment" if "actual_payment" in layout_cols else "NULL AS actual_payment"
            layout = conn.execute(
                f"""
                SELECT row_index,employee_id,employee_name_snapshot,work_type_id,
                       work_name_snapshot,work_code_snapshot,price_snapshot,hours,
                       fixed_boxes,fixed_weight,fixed_total,{fixed_payment_sql},actual_value,{actual_payment_sql},payment
                FROM work_order_layout_rows WHERE order_id=? ORDER BY row_index
                """, (order_id,),
            ).fetchall()
            if layout:
                lines = [OrderLine(
                    employee_id=r[1], employee_name=str(r[2] or ""), work_type_id=r[3],
                    work_name=str(r[4] or ""), work_code=str(r[5] or ""), price=dec(r[6]),
                    hours=dec(r[7]), fixed_boxes=dec(r[8]), fixed_weight=dec(r[9]), actual_value=dec(r[12]),
                ) for r in layout]
            else:
                old = conn.execute(
                    """
                    SELECT i.employee_id,COALESCE(e.name,''),i.work_type_id,
                           COALESCE(i.work_name_snapshot,w.name,''),COALESCE(i.work_code_snapshot,w.code,''),
                           COALESCE(i.price_snapshot,w.price),i.hours,i.fixed_boxes,i.fixed_weight,i.actual_value
                    FROM work_order_items i
                    LEFT JOIN employees e ON e.id=i.employee_id
                    LEFT JOIN work_types w ON w.id=i.work_type_id
                    WHERE i.order_id=? ORDER BY i.id
                    """, (order_id,),
                ).fetchall()
                lines = [OrderLine(
                    employee_id=r[0], employee_name=str(r[1] or ""), work_type_id=r[2],
                    work_name=str(r[3] or ""), work_code=str(r[4] or ""), price=dec(r[5]),
                    hours=dec(r[6]), fixed_boxes=dec(r[7]), fixed_weight=dec(r[8]), actual_value=dec(r[9]),
                ) for r in old]
        return {"info": dict(info), "lines": lines}

    def save_order(
        self, actor: SessionUser, order_date: str, shift_type: str, master_id: int,
        department_id: int, lines: list[OrderLine], comment: str = "",
        parent_id: int | None = None, separate_worker: bool = False,
    ) -> int:
        # Keep employee-only layout rows so workers without assigned works survive save/reopen.
        layout_rows = [
            ln for ln in lines
            if (
                ln.employee_id is not None or ln.employee_name.strip()
                or ln.work_type_id is not None or ln.work_name.strip()
            )
        ]
        meaningful = [ln for ln in layout_rows if ln.work_type_id is not None or ln.work_name.strip()]
        if not meaningful:
            raise ValueError("Наряд не содержит работ")
        stamp = now_text()
        self._ensure_optional_schema()
        with self.write_conn(retries=8) as conn:
            if parent_id is None:
                roots = conn.execute("SELECT version FROM work_orders WHERE instr(version,'.')=0").fetchall()
                max_base = max([int(r[0]) for r in roots if str(r[0]).isdigit()] or [0])
                version = str(max_base + 1)
            else:
                parent = conn.execute("SELECT version FROM work_orders WHERE id=?", (parent_id,)).fetchone()
                if not parent: raise DatabaseError("Исходная версия наряда не найдена")
                base = self._base_version(str(parent[0])); latest = self._latest_for_base_conn(conn, base)
                if not latest or int(latest[0]) != int(parent_id):
                    raise StaleOrderError("Редактировать можно только последнюю версию наряда")
                version = f"{base}.{self._revision(str(parent[0])) + 1}"
            cur = conn.execute(
                """INSERT INTO work_orders(order_date,shift_type,master_id,department_id,registration_date,version,parent_id,status,edited_by,edit_date,comment,separate_worker)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order_date,shift_type,master_id,department_id,stamp,version,parent_id,"saved",actor.username,stamp,comment.strip(),1 if separate_worker else 0),
            )
            order_id = int(cur.lastrowid)
            layout_cols = self._columns(conn, "work_order_layout_rows")
            has_fp = "fixed_payment" in layout_cols; has_ap = "actual_payment" in layout_cols
            for idx,line in enumerate(layout_rows):
                price=float(line.price) if line.price is not None else None; hours=float(line.hours) if line.hours is not None else None
                boxes=float(line.fixed_boxes) if line.fixed_boxes is not None else None; weight=float(line.fixed_weight) if line.fixed_weight is not None else None
                actual=float(line.actual_value) if line.actual_value is not None else None; fixed_total=float(line.fixed_total) if line.fixed_total is not None else None
                fixed_payment=float(line.fixed_payment) if line.fixed_payment is not None else None; actual_payment=float(line.actual_payment) if line.actual_payment is not None else None
                legacy_payment = fixed_payment if fixed_payment is not None else actual_payment
                has_work = line.work_type_id is not None or bool(line.work_name.strip())
                if has_work:
                    conn.execute(
                        """INSERT INTO work_order_items(order_id,employee_id,work_type_id,hours,fixed_boxes,fixed_weight,actual_value,work_name_snapshot,work_code_snapshot,price_snapshot)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (order_id,line.employee_id,line.work_type_id,hours,boxes,weight,actual,line.work_name,line.work_code,price),
                    )
                columns=["order_id","row_index","employee_id","employee_name_snapshot","work_type_id","work_name_snapshot","work_code_snapshot","price_snapshot","hours","fixed_boxes","fixed_weight","fixed_total"]
                values=[order_id,idx,line.employee_id,line.employee_name,line.work_type_id,line.work_name,line.work_code,price,hours,boxes,weight,fixed_total]
                if has_fp: columns.append("fixed_payment"); values.append(fixed_payment)
                columns.append("actual_value"); values.append(actual)
                if has_ap: columns.append("actual_payment"); values.append(actual_payment)
                columns.extend(["payment","created_at"]); values.extend([legacy_payment,stamp])
                conn.execute(f"INSERT INTO work_order_layout_rows({','.join(columns)}) VALUES({','.join('?' for _ in values)})", values)
            self._audit_conn(
                conn, actor.username, "Создал" if parent_id is None else "Отредактировал",
                "Наряд", version,
                f"Работ: {len(meaningful)}; строк макета: {len(layout_rows)}; parent_id={parent_id or ''}",
            )
            self._record_order_notification_conn(conn,actor,order_id,version,parent_id,comment.strip(),stamp)
            from .order_files import enqueue_conn
            enqueue_conn(conn, order_id)
        return order_id

    @staticmethod
    def _record_order_notification_conn(conn,actor,order_id,version,parent_id,comment,stamp):
        # These records commit atomically with the new version. Failed/stale
        # saves and rollbacks therefore cannot create phantom notifications.
        conn.execute("""CREATE TABLE IF NOT EXISTS order_owners (
            base_version TEXT PRIMARY KEY,user_id INTEGER,username TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS order_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER,owner_username TEXT NOT NULL,
            actor_username TEXT NOT NULL,actor_role TEXT NOT NULL,order_id INTEGER NOT NULL,
            base_version TEXT NOT NULL,version TEXT NOT NULL,message TEXT NOT NULL,
            created_at TEXT NOT NULL,read_at TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notification_owner ON order_notifications(owner_id,read_at,id)")
        base=str(version).split('.',1)[0]
        if parent_id is None:
            conn.execute("INSERT OR IGNORE INTO order_owners(base_version,user_id,username) VALUES(?,?,?)",(base,actor.id,actor.username))
            return
        owner=conn.execute("SELECT user_id,username FROM order_owners WHERE base_version=?",(base,)).fetchone()
        if owner is None:
            root=conn.execute("SELECT edited_by FROM work_orders WHERE version=? ORDER BY id LIMIT 1",(base,)).fetchone()
            if not root or not str(root[0] or '').strip():return
            owner=(None,str(root[0]))
        if owner[0]==actor.id or owner[1]==actor.username:return
        parent=conn.execute("SELECT comment FROM work_orders WHERE id=?",(parent_id,)).fetchone()
        previous=str(parent[0] or '') if parent else ''
        who=("Мастер "+actor.username) if str(actor.role).startswith("Мастер") else (actor.role+" "+actor.username)
        action="оставил комментарий в" if comment and comment!=previous else "изменил комментарий в" if comment!=previous else "изменил"
        message=f"{who} {action} Вашем наряде № {base}. Посмотреть в версии {version}." if action!="изменил" else f"{who} изменил Ваш наряд № {base}. Посмотреть в версии {version}."
        if comment and comment!=previous:message+="\nКомментарий: "+comment
        conn.execute("""INSERT INTO order_notifications(owner_id,owner_username,actor_username,actor_role,order_id,
            base_version,version,message,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            (owner[0],owner[1],actor.username,actor.role,order_id,base,version,message,stamp))

    def read_archive_orders(self, archive_path: str | os.PathLike[str], limit: int = 1000) -> list[sqlite3.Row]:
        """Read an archive snapshot without touching the active DB connection."""
        path = Path(archive_path)
        if not path.exists(): raise FileNotFoundError(path)
        # Open UNC/filesystem paths directly. Building file: URIs from UNC paths
        # makes sqlite interpret the server name as an unsupported URI authority.
        conn = sqlite3.connect(str(path), timeout=1.5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        try:
            return conn.execute(
                """SELECT wo.version,wo.order_date,wo.shift_type,COALESCE(e.name,''),COALESCE(d.name,''),wo.registration_date
                   FROM work_orders wo LEFT JOIN employees e ON e.id=wo.master_id LEFT JOIN departments d ON d.id=wo.department_id
                   WHERE COALESCE(wo.status,'saved')='saved' ORDER BY wo.id DESC LIMIT ?""",
                (max(1,min(int(limit),5000)),),
            ).fetchall()
        finally:
            conn.close()

    # ---------- edit locks ----------
    def acquire_edit_lock(self, order_id: int, user: SessionUser, stale_seconds: int = 120) -> tuple[str | None, dict | None]:
        self._ensure_optional_schema()
        token = uuid.uuid4().hex
        key = f"order:{order_id}"
        now = time.time()
        with self.write_conn() as conn:
            conn.execute("DELETE FROM work_order_edit_locks WHERE heartbeat_at<?", (now - stale_seconds,))
            row = conn.execute(
                "SELECT username,role,computer,process_id,acquired_at,token FROM work_order_edit_locks WHERE lock_key=?",
                (key,),
            ).fetchone()
            if row:
                return None, dict(row)
            conn.execute(
                """
                INSERT INTO work_order_edit_locks(lock_key,order_id,username,role,computer,process_id,token,acquired_at,heartbeat_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (key, order_id, user.username, user.role, socket.gethostname(), os.getpid(), token, now, now),
            )
        return token, None

    def heartbeat_edit_lock(self, order_id: int, token: str) -> bool:
        with self.write_conn(retries=3) as conn:
            cur = conn.execute(
                "UPDATE work_order_edit_locks SET heartbeat_at=? WHERE lock_key=? AND token=?",
                (time.time(), f"order:{order_id}", token),
            )
            return cur.rowcount == 1

    def release_edit_lock(self, order_id: int, token: str) -> None:
        try:
            with self.write_conn(retries=3) as conn:
                conn.execute("DELETE FROM work_order_edit_locks WHERE lock_key=? AND token=?", (f"order:{order_id}", token))
        except Exception:
            pass

    # ---------- audit ----------
    @staticmethod
    def _audit_conn(conn: sqlite3.Connection, username: str, action: str, object_type: str, object_name: str, details: str) -> None:
        conn.execute(
            "INSERT INTO audit_log(timestamp,username,action,object_type,object_name,details) VALUES(?,?,?,?,?,?)",
            (now_text(), username or "Система", action, object_type, object_name, details),
        )

    def log_action(self, username: str, action: str, object_type: str = "", object_name: str = "", details: str = "") -> None:
        with self.write_conn() as conn:
            self._audit_conn(conn, username, action, object_type, object_name, details)

    def recent_audit(self, limit: int = 200) -> list[sqlite3.Row]:
        with self.read_conn() as conn:
            return conn.execute(
                "SELECT timestamp,username,action,object_type,object_name,details FROM audit_log ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()

    def change_token(self) -> int:
        """Cheap cross-client revision token used by the UI watcher.

        Every user-visible write in SmartOrder records an audit row in the same
        transaction, so MAX(audit_log.id) is a compact shared change sequence.
        The call is deliberately read-only and uses one short connection.
        """
        with self.read_conn() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id),0) FROM audit_log").fetchone()
            return int(row[0] or 0) if row else 0

    # ---------- health / backup ----------
    def ping_ms(self) -> float:
        return self.stable_ping_ms()

    def stable_ping_ms(self, samples: int = 3) -> float:
        """Warm SMB once, then report median working SQLite response time."""
        values: list[float] = []
        with self.read_conn() as conn:
            # Warm-up is deliberately excluded from the displayed number.
            conn.execute("SELECT value FROM db_meta WHERE key='active_month'").fetchone()
            for _ in range(max(3, int(samples))):
                started = time.perf_counter()
                conn.execute("SELECT value FROM db_meta WHERE key='active_month'").fetchone()
                values.append(max(0.1, (time.perf_counter() - started) * 1000.0))
        return float(statistics.median(values))

    def quick_check(self) -> str:
        """Run SQLite quick_check on a short read-only connection."""
        with self.read_conn() as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
            if not row:
                return "unknown"
            return str(row[0])

    def backup_to(self, target: Path, verify: bool = True) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        src = self._connect(6.0)
        dst = sqlite3.connect(str(target), timeout=6.0)
        try:
            src.backup(dst, pages=512, sleep=0.02)
            dst.commit()
            if verify:
                row = dst.execute("PRAGMA quick_check").fetchone()
                if not row or str(row[0]).lower() != "ok":
                    raise DatabaseError(f"quick_check: {row}")
            return target
        except Exception:
            try:
                dst.close()
            finally:
                src.close()
            try:
                target.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        finally:
            try:
                dst.close()
            except Exception:
                pass
            try:
                src.close()
            except Exception:
                pass

    def restore_from(self, source: Path) -> None:
        if not source.exists():
            raise FileNotFoundError(source)
        src = sqlite3.connect(str(source), timeout=8.0)
        check = src.execute("PRAGMA quick_check").fetchone()
        if not check or str(check[0]).lower() != "ok":
            src.close()
            raise DatabaseError("Выбранная резервная копия повреждена")
        dst = self._connect(8.0)
        try:
            src.backup(dst, pages=512, sleep=0.03)
            dst.commit()
        finally:
            src.close()
            dst.close()
        self.invalidate_cache()
        self._reference_authors_ready = False
        self._invalidate_local_compat_marker()
        self._ensure_schema()
        self._write_local_compat_marker()


# ===========================================================================
# RC18 — audit filters, recycle restore and catalog recycle view
# ===========================================================================

def _rc18_audit_usernames(self) -> list[str]:
    with self.read_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT username FROM audit_log WHERE COALESCE(username,'')<>'' ORDER BY username COLLATE NOCASE"
        ).fetchall()
    return [str(r[0]) for r in rows if str(r[0] or "").strip()]


def _rc18_recent_audit_filtered(
    self,
    date_from: str | None = None,
    date_to: str | None = None,
    username: str | None = None,
    limit: int = 500,
) -> list[sqlite3.Row]:
    clauses = []
    params: list[object] = []
    date_expr = "substr(timestamp,7,4)||'-'||substr(timestamp,4,2)||'-'||substr(timestamp,1,2)"
    if date_from:
        clauses.append(f"{date_expr}>=?")
        params.append(str(date_from))
    if date_to:
        clauses.append(f"{date_expr}<=?")
        params.append(str(date_to))
    if username:
        clauses.append("username=?")
        params.append(str(username))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(max(1, min(int(limit), 5000)))
    with self.read_conn() as conn:
        return conn.execute(
            "SELECT timestamp,username,action,object_type,object_name,details "
            f"FROM audit_log{where} ORDER BY id DESC LIMIT ?",
            tuple(params),
        ).fetchall()


def _rc18_list_recent_deleted_work_types(self, days: int = RECENT_DELETED_DAYS) -> list[sqlite3.Row]:
    cutoff = datetime.now() - timedelta(days=max(1, int(days)))
    try:
        with self.read_conn() as conn:
            rows = conn.execute(
                """
                SELECT w.id,w.name,w.code,w.price,w.registration_date,w.edit_date,s.marked_at,s.marked_by
                FROM work_types w
                JOIN soft_deleted_entities s
                  ON s.entity_type='work_type' AND s.entity_id=w.id
                ORDER BY s.marked_at DESC,w.name COLLATE NOCASE
                """
            ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise
    result = []
    for row in rows:
        try:
            marked_at = datetime.strptime(str(row[6]), DT_FMT)
        except Exception:
            continue
        if marked_at >= cutoff:
            result.append(row)
    return result


def _rc18_restore_soft_deleted(self, actor: SessionUser, entity_type: str, entity_id: int) -> None:
    entity_type = str(entity_type)
    entity_id = int(entity_id)
    with self.write_conn() as conn:
        self._ensure_soft_delete_schema_conn(conn)
        marker = conn.execute(
            "SELECT 1 FROM soft_deleted_entities WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id),
        ).fetchone()
        if not marker:
            raise DatabaseError("Запись не находится в списке недавно удалённых.")
        if entity_type == "employee":
            row = conn.execute("SELECT name,is_master FROM employees WHERE id=?", (entity_id,)).fetchone()
            if not row:
                raise DatabaseError("Сотрудник не найден.")
            name = str(row[0]); kind = "Мастер" if bool(row[1]) else "Сотрудник"
        elif entity_type == "department":
            row = conn.execute("SELECT name FROM departments WHERE id=?", (entity_id,)).fetchone()
            if not row:
                raise DatabaseError("Подразделение не найдено.")
            name = str(row[0]); kind = "Подразделение"
        elif entity_type == "work_type":
            row = conn.execute("SELECT name FROM work_types WHERE id=?", (entity_id,)).fetchone()
            if not row:
                raise DatabaseError("Работа не найдена.")
            name = str(row[0]); kind = "Номенклатура"
        else:
            raise DatabaseError("Неизвестный тип восстанавливаемой записи.")
        conn.execute(
            "DELETE FROM soft_deleted_entities WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id),
        )
        self._audit_conn(conn, actor.username, "Восстановил", kind, name, f"id={entity_id}")
    self.invalidate_cache("employees", "departments", "work_types", "soft_deleted")


def _rc18_order_creator(self, order_id: int) -> str:
    with self.read_conn() as conn:
        row = conn.execute(
            "SELECT version,COALESCE(edited_by,'') FROM work_orders WHERE id=?",
            (int(order_id),),
        ).fetchone()
        if not row:
            return ""
        version, edited_by = str(row[0] or ""), str(row[1] or "").strip()
        base = version.split(".", 1)[0]
        root = conn.execute(
            """
            SELECT id,version,COALESCE(edited_by,'') FROM work_orders
            WHERE CASE WHEN instr(version,'.')>0 THEN substr(version,1,instr(version,'.')-1) ELSE version END=?
            ORDER BY id ASC LIMIT 1
            """,
            (base,),
        ).fetchone()
        if root and str(root[2] or "").strip():
            return str(root[2]).strip()
        target_version = str(root[1] if root else version)
        audit = conn.execute(
            """
            SELECT username FROM audit_log
            WHERE action='Создал' AND object_type='Наряд' AND object_name=?
              AND COALESCE(username,'')<>''
            ORDER BY id ASC LIMIT 1
            """,
            (target_version,),
        ).fetchone()
        return str(audit[0]).strip() if audit else edited_by


Database.audit_usernames = _rc18_audit_usernames
Database.recent_audit_filtered = _rc18_recent_audit_filtered
Database.list_recent_deleted_work_types = _rc18_list_recent_deleted_work_types
Database.restore_soft_deleted = _rc18_restore_soft_deleted
Database.order_creator = _rc18_order_creator


# RC18 recycle-bin semantics: every manual delete spends 30 days in the
# "Недавно удалённые" view, even if the entity has no historical references.
def _rc18_delete_employee(self, actor: SessionUser, employee_id: int) -> str:
    employee_id=int(employee_id)
    with self.write_conn() as conn:
        row=conn.execute("SELECT name,is_master FROM employees WHERE id=?",(employee_id,)).fetchone()
        if not row:
            raise DatabaseError("Сотрудник не найден.")
        name,is_master=str(row[0]),bool(row[1])
        master_count=int(conn.execute("SELECT COUNT(*) FROM work_orders WHERE master_id=?",(employee_id,)).fetchone()[0] or 0)
        item_count=int(conn.execute("SELECT COUNT(*) FROM work_order_items WHERE employee_id=?",(employee_id,)).fetchone()[0] or 0)
        try:
            layout_count=int(conn.execute("SELECT COUNT(*) FROM work_order_layout_rows WHERE employee_id=?",(employee_id,)).fetchone()[0] or 0)
        except sqlite3.OperationalError:
            layout_count=0
        used=master_count+item_count+layout_count
        self._mark_soft_deleted_conn(conn,"employee",employee_id,actor)
        self._audit_conn(
            conn,actor.username,"Пометил на удаление",
            "Мастер" if is_master else "Сотрудник",name,
            f"Связанных записей: {used}; хранение в корзине: {RECENT_DELETED_DAYS} дней",
        )
    self.invalidate_cache("employees","soft_deleted")
    return "marked"


def _rc18_delete_department(self, actor: SessionUser, department_id: int) -> str:
    department_id=int(department_id)
    with self.write_conn() as conn:
        row=conn.execute("SELECT name FROM departments WHERE id=?",(department_id,)).fetchone()
        if not row:
            raise DatabaseError("Подразделение не найдено.")
        name=str(row[0])
        used=int(conn.execute("SELECT COUNT(*) FROM work_orders WHERE department_id=?",(department_id,)).fetchone()[0] or 0)
        self._mark_soft_deleted_conn(conn,"department",department_id,actor)
        self._audit_conn(conn,actor.username,"Пометил на удаление","Подразделение",name,
                         f"Связанных нарядов: {used}; хранение в корзине: {RECENT_DELETED_DAYS} дней")
    self.invalidate_cache("departments","soft_deleted")
    return "marked"


def _rc18_delete_work_type(self, actor: SessionUser, work_id: int) -> str:
    work_id=int(work_id)
    with self.write_conn() as conn:
        row=conn.execute("SELECT name FROM work_types WHERE id=?",(work_id,)).fetchone()
        if not row:
            raise DatabaseError("Работа не найдена или уже удалена.")
        name=str(row[0] or work_id)
        item_count=int(conn.execute("SELECT COUNT(*) FROM work_order_items WHERE work_type_id=?",(work_id,)).fetchone()[0] or 0)
        try:
            layout_count=int(conn.execute("SELECT COUNT(*) FROM work_order_layout_rows WHERE work_type_id=?",(work_id,)).fetchone()[0] or 0)
        except sqlite3.OperationalError:
            layout_count=0
        used=item_count+layout_count
        self._mark_soft_deleted_conn(conn,"work_type",work_id,actor)
        self._audit_conn(conn,actor.username,"Пометил на удаление","Номенклатура",name,
                         f"Связанных записей: {used}; хранение в корзине: {RECENT_DELETED_DAYS} дней")
    self.invalidate_cache("work_types","soft_deleted")
    return "marked"


_RC18_PREVIOUS_RETENTION = Database.run_retention_maintenance

def _rc18_run_retention_maintenance(self, force: bool=False):
    stats=_RC18_PREVIOUS_RETENTION(self,force)
    stats.setdefault("work_types",0)
    today=datetime.now().strftime("%Y-%m-%d")
    recent_cutoff=datetime.now()-timedelta(days=RECENT_DELETED_DAYS)
    # Separate guard so an RC17 maintenance earlier on the same day does not
    # permanently skip RC18 catalog cleanup.
    try:
        if not force:
            with self.read_conn() as conn:
                row=conn.execute("SELECT value FROM db_meta WHERE key='retention_worktypes_last_run'").fetchone()
            if row and str(row[0])==today:
                return stats
    except Exception:
        pass
    with self.write_conn(retries=8) as conn:
        self._ensure_soft_delete_schema_conn(conn)
        markers=conn.execute(
            "SELECT entity_id,marked_at FROM soft_deleted_entities WHERE entity_type='work_type'"
        ).fetchall()
        removed=0
        for entity_id,marked_at_text in markers:
            try:
                marked_at=datetime.strptime(str(marked_at_text),DT_FMT)
            except Exception:
                continue
            if marked_at>recent_cutoff:
                continue
            entity_id=int(entity_id)
            refs=int(conn.execute("SELECT COUNT(*) FROM work_order_items WHERE work_type_id=?",(entity_id,)).fetchone()[0] or 0)
            try:
                refs+=int(conn.execute("SELECT COUNT(*) FROM work_order_layout_rows WHERE work_type_id=?",(entity_id,)).fetchone()[0] or 0)
            except sqlite3.OperationalError:
                pass
            if refs==0:
                conn.execute("DELETE FROM work_type_prices WHERE work_type_id=?",(entity_id,))
                conn.execute("DELETE FROM work_types WHERE id=?",(entity_id,))
                conn.execute("DELETE FROM soft_deleted_entities WHERE entity_type='work_type' AND entity_id=?",(entity_id,))
                removed+=1
        conn.execute(
            "INSERT INTO db_meta(key,value) VALUES('retention_worktypes_last_run',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",(today,)
        )
        stats["work_types"]=removed
    self.invalidate_cache("work_types","soft_deleted")
    return stats


Database.delete_employee=_rc18_delete_employee
Database.delete_department=_rc18_delete_department
Database.delete_work_type=_rc18_delete_work_type
Database.run_retention_maintenance=_rc18_run_retention_maintenance

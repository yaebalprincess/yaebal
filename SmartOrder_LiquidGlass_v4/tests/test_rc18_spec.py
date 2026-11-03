
from pathlib import Path
import tempfile

from smartorder.db import Database
from smartorder.security import SessionUser

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")
POLICY = (ROOT / "smartorder" / "policy.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "smartorder" / "config.py").read_text(encoding="utf-8")
STYLES = (ROOT / "smartorder" / "heavy_styles.py").read_text(encoding="utf-8")


def _db():
    tmp = tempfile.TemporaryDirectory()
    db = Database(Path(tmp.name) / "work_orders.db")
    db.create_first_admin("admin", "password123")
    admin = db.authenticate("admin", "password123")
    return tmp, db, admin


def test_rc18_version():
    assert 'APP_VERSION = "1.0"' in CONFIG


def test_sync_is_logged_and_audit_filters_exist():
    assert '"Синхронизировал"' in HEAVY
    assert 'self.audit_date_filter = DateRangeEdit()' in HEAVY
    assert 'self.audit_user_filter = SmartComboBox()' in HEAVY
    assert 'recent_audit_filtered' in HEAVY


def test_database_audit_filter_and_user_list():
    tmp, db, admin = _db()
    try:
        db.log_action("admin", "Синхронизировал", "База данных", "work_orders.db", "ПК: TEST")
        db.log_action("other", "Тест", "Система", "x", "")
        assert "admin" in db.audit_usernames()
        rows = db.recent_audit_filtered(username="admin")
        assert any(str(r[2]) == "Синхронизировал" for r in rows)
        assert all(str(r[1]) == "admin" for r in rows)
    finally:
        tmp.cleanup()


def test_recycle_restore_for_people_department_and_work():
    tmp, db, admin = _db()
    try:
        worker = db.add_employee(admin, "Работник", False)
        dep = db.add_department(admin, "1. Цех")
        work = db.add_work_type(admin, "Работа", "R1", "1")
        assert db.delete_employee(admin, worker) == "marked"
        assert db.delete_department(admin, dep) == "marked"
        assert db.delete_work_type(admin, work) == "marked"
        assert any(int(r[0]) == work for r in db.list_recent_deleted_work_types())
        db.restore_soft_deleted(admin, "employee", worker)
        db.restore_soft_deleted(admin, "department", dep)
        db.restore_soft_deleted(admin, "work_type", work)
        assert not db.is_soft_deleted("employee", worker)
        assert not db.is_soft_deleted("department", dep)
        assert not db.is_soft_deleted("work_type", work)
    finally:
        tmp.cleanup()


def test_catalog_recent_context_and_restore_are_present():
    assert 'self.work_recent_btn = QPushButton("Недавно удалённые")' in HEAVY
    assert 'Восстановить (только для Администратора)' in HEAVY
    assert 'Копировать' in HEAVY
    assert 'Редактировать' in HEAVY
    assert 'Удалить' in HEAVY
    assert 'item.column() not in (0, 1)' in HEAVY


def test_people_delete_prompts_are_explicit():
    assert 'Удалить работника "{name}" ?' in HEAVY
    assert 'Удалить мастера "{name}" ?' in HEAVY
    assert 'Удалить подразделение "{name}" ?' in HEAVY


def test_about_layout_and_support_links():
    assert 'Документация' in HEAVY
    assert 'Возможные проблемы при работе с SmartOrder V 1.0' in HEAVY
    assert 'https://tmbsir.ru/' in HEAVY
    assert 'https://sir01.bitrix24.ru/company/personal/user/1292/' in HEAVY
    assert 'Bitrix24:' in HEAVY
    assert 'Помощь' in HEAVY


def test_docs_include_zoom_shortcuts_and_v1_troubleshooting():
    assert 'Ctrl+' in POLICY
    assert 'Ctrl-' in POLICY
    assert 'Возможные проблемы при работе с SmartOrder V 1.0' in POLICY


def test_order_number_is_compact_and_history_creator_fallback_exists():
    assert 'chip.setStyleSheet("background:transparent' in HEAVY
    assert 'self.db.order_creator(ref)' in HEAVY
    assert 'Создал: Система' in HEAVY


def test_zoom_is_debounced_and_shortcuts_exist():
    assert 'self._rc18_zoom_timer.setInterval(85)' in HEAVY
    assert '("Ctrl++", 10)' in HEAVY
    assert '("Ctrl+-", -10)' in HEAVY
    assert 'QScrollArea' in HEAVY
    assert 'compact=min(z,1.50)' in STYLES
    assert 'input_h=max(34,int(34*compact))' in STYLES


def test_heavy_ui_still_has_no_direct_sqlite_calls():
    assert "sqlite3.connect(" not in HEAVY
    assert "self.db.conn" not in HEAVY
    assert ".commit()" not in HEAVY

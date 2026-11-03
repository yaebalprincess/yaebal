from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import tempfile

from smartorder.db import Database, DT_FMT
from smartorder.domain import OrderLine


def fixture():
    tmp = tempfile.TemporaryDirectory()
    db = Database(Path(tmp.name) / "work_orders.db")
    db.create_first_admin("admin", "password123")
    admin = db.authenticate("admin", "password123")
    master = db.add_employee(admin, "Мастер", True)
    worker = db.add_employee(admin, "Работник", False)
    dep = db.add_department(admin, "1. Цех")
    work = db.add_work_type(admin, "Работа", "R1", "2.5")
    return tmp, db, admin, master, worker, dep, work


def save(db, admin, master, dep, worker, work):
    return db.save_order(
        admin, "24-09-2026", "Дневная", master, dep,
        [OrderLine(worker, "Работник", work, "Работа", "R1", Decimal("2.5"), actual_value=Decimal("2"))],
    )


def test_used_department_moves_to_soft_delete_and_active_list_hides_it():
    tmp, db, admin, master, worker, dep, work = fixture()
    try:
        oid = save(db, admin, master, dep, worker, work)
        assert db.delete_department(admin, dep) == "marked"
        assert db.is_soft_deleted("department", dep)
        assert not any(int(r[0]) == dep for r in db.get_active_departments())
        assert any(int(r[0]) == dep for r in db.list_recent_deleted_departments())
        assert db.get_order(oid) is not None
    finally:
        tmp.cleanup()


def test_recent_deleted_people_disappear_from_recycle_view_after_30_days_but_stay_hidden_if_referenced():
    tmp, db, admin, master, worker, dep, work = fixture()
    try:
        save(db, admin, master, dep, worker, work)
        assert db.delete_employee(admin, worker) == "marked"
        assert any(int(r[0]) == worker for r in db.list_recent_deleted_employees(False))
        old = (datetime.now() - timedelta(days=31)).strftime(DT_FMT)
        with db.write_conn() as conn:
            conn.execute("UPDATE soft_deleted_entities SET marked_at=? WHERE entity_type='employee' AND entity_id=?", (old, worker))
        db.invalidate_cache("soft_deleted")
        assert not any(int(r[0]) == worker for r in db.list_recent_deleted_employees(False))
        assert not any(int(r[0]) == worker for r in db.get_active_employees(False))
        # Still physically retained because a non-expired order references it.
        assert any(int(r[0]) == worker for r in db.get_employees(False))
    finally:
        tmp.cleanup()


def test_order_family_is_removed_after_one_year_and_old_tombstone_can_then_be_purged():
    tmp, db, admin, master, worker, dep, work = fixture()
    try:
        oid = save(db, admin, master, dep, worker, work)
        assert db.delete_employee(admin, worker) == "marked"
        assert db.delete_department(admin, dep) == "marked"
        old_order = (datetime.now() - timedelta(days=366)).strftime(DT_FMT)
        old_marker = (datetime.now() - timedelta(days=31)).strftime(DT_FMT)
        with db.write_conn() as conn:
            conn.execute("UPDATE work_orders SET registration_date=? WHERE id=?", (old_order, oid))
            conn.execute("UPDATE soft_deleted_entities SET marked_at=? WHERE entity_type='employee' AND entity_id=?", (old_marker, worker))
            conn.execute("UPDATE soft_deleted_entities SET marked_at=? WHERE entity_type='department' AND entity_id=?", (old_marker, dep))
        stats = db.run_retention_maintenance(force=True)
        assert int(stats["orders"]) == 1
        assert db.get_order(oid) is None
        assert not any(int(r[0]) == worker for r in db.get_employees(False))
        assert not any(int(r[0]) == dep for r in db.get_departments())
    finally:
        tmp.cleanup()


def test_new_order_is_not_removed_by_retention():
    tmp, db, admin, master, worker, dep, work = fixture()
    try:
        oid = save(db, admin, master, dep, worker, work)
        stats = db.run_retention_maintenance(force=True)
        assert int(stats["orders"]) == 0
        assert db.get_order(oid) is not None
    finally:
        tmp.cleanup()


def test_rc17_ui_has_recent_deleted_toggle_and_final_aliases():
    root = Path(__file__).resolve().parents[1]
    heavy = (root / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")
    assert 'class RC17MainWindow' in heavy
    assert 'Недавно удалённые' in heavy
    assert '← Текущие' in heavy
    assert 'list_recent_deleted_departments(30)' in heavy
    assert 'list_recent_deleted_employees(mode == "master", 30)' in heavy
    assert 'MainWindow = RC17MainWindow' in heavy
    assert 'WorkOrderDialog = RC17WorkOrderDialog' in heavy

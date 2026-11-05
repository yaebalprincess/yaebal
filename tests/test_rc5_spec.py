import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from smartorder.db import Database, DatabaseError
from smartorder.domain import OrderLine


class RC5SpecificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "work_orders.db"
        self.db = Database(self.path)
        self.db.create_first_admin("admin", "password123")
        self.admin = self.db.authenticate("admin", "password123")
        self.master = self.db.add_employee(self.admin, "Мастер", True)
        self.dep = self.db.add_department(self.admin, "Обычный цех")
        self.w1 = self.db.add_employee(self.admin, "Работник 1", False)
        self.w2 = self.db.add_employee(self.admin, "Работник 2", False)
        self.w3 = self.db.add_employee(self.admin, "Работник 3", False)
        self.work1 = self.db.add_work_type(self.admin, "Работа 1", "R1", "2.5")
        self.work2 = self.db.add_work_type(self.admin, "Работа 2", "R2", "4")

    def tearDown(self):
        self.tmp.cleanup()

    def line(self, emp, name, work=None, wname="", code="", price=None):
        return OrderLine(
            emp, name, work, wname, code,
            Decimal(str(price)) if price is not None else None,
        )

    def test_employee_only_layout_row_survives_save_reopen(self):
        lines = [
            self.line(self.w1, "Работник 1", self.work1, "Работа 1", "R1", "2.5"),
            self.line(self.w2, "Работник 2", self.work2, "Работа 2", "R2", "4"),
            self.line(self.w3, "Работник 3"),
        ]
        oid = self.db.save_order(
            self.admin, "28-08-2026", "Дневная", self.master, self.dep, lines
        )
        loaded = self.db.get_order(oid)["lines"]
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[2].employee_name, "Работник 3")
        self.assertIsNone(loaded[2].work_type_id)

    def test_delete_referenced_catalog_item_is_friendly_and_safe(self):
        oid = self.db.save_order(
            self.admin, "28-08-2026", "Дневная", self.master, self.dep,
            [self.line(self.w1, "Работник 1", self.work1, "Работа 1", "R1", "2.5")],
        )
        result = self.db.delete_work_type(self.admin, self.work1)
        self.assertEqual(result, "marked")
        self.assertTrue(self.db.is_soft_deleted("work_type", self.work1))
        self.assertTrue(any(int(r[0]) == self.work1 for r in self.db.get_work_types()))
        self.assertFalse(any(int(r[0]) == self.work1 for r in self.db.get_active_work_types()))
        self.assertIsNotNone(self.db.get_order(oid))

    def test_delete_unused_catalog_item_deletes_price_history_first(self):
        extra = self.db.add_work_type(self.admin, "Удаляемая", "DEL", "1")
        result = self.db.delete_work_type(self.admin, extra)
        self.assertEqual(result, "marked")
        self.assertTrue(self.db.is_soft_deleted("work_type", extra))
        self.assertTrue(any(int(r[0]) == extra for r in self.db.get_work_types()))
        self.assertFalse(any(int(r[0]) == extra for r in self.db.get_active_work_types()))

    def test_archive_snapshot_can_be_read(self):
        self.db.save_order(
            self.admin, "28-08-2026", "Дневная", self.master, self.dep,
            [self.line(self.w1, "Работник 1", self.work1, "Работа 1", "R1", "2.5")],
        )
        snap = Path(self.tmp.name) / "archive.db"
        self.db.backup_to(snap)
        rows = self.db.read_archive_orders(snap)
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0][0]), "1")

    def test_two_database_instances_can_create_orders_concurrently(self):
        db2 = Database(self.path)
        errors = []
        start = threading.Barrier(2)

        def worker(db, prefix):
            try:
                start.wait(timeout=3)
                for i in range(8):
                    db.save_order(
                        self.admin, "28-08-2026", "Дневная", self.master, self.dep,
                        [self.line(self.w1, "Работник 1", self.work1, "Работа 1", "R1", "2.5")],
                        f"{prefix}{i}",
                    )
            except Exception as exc:
                errors.append(exc)

        a = threading.Thread(target=worker, args=(self.db, "A"))
        b = threading.Thread(target=worker, args=(db2, "B"))
        a.start(); b.start(); a.join(20); b.join(20)
        self.assertFalse(errors, errors)
        rows = self.db.list_orders(limit=100)
        self.assertEqual(len(rows), 16)
        self.assertEqual(len({str(r[1]) for r in rows}), 16)


if __name__ == "__main__":
    unittest.main()

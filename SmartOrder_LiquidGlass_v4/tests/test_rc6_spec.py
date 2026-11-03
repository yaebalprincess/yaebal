import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from smartorder.db import Database, DatabaseError
from smartorder.domain import OrderLine


class RC6SpecificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "work_orders.db")
        self.db.create_first_admin("admin", "password123")
        self.admin = self.db.authenticate("admin", "password123")
        self.master = self.db.add_employee(self.admin, "Мастер", True)
        self.worker = self.db.add_employee(self.admin, "Работник", False)
        self.dep = self.db.add_department(self.admin, "Цех")
        self.work = self.db.add_work_type(self.admin, "Работа", "R1", "1")

    def tearDown(self):
        self.tmp.cleanup()

    def saved_order(self):
        return self.db.save_order(
            self.admin, "28-08-2026", "Дневная", self.master, self.dep,
            [OrderLine(self.worker, "Работник", self.work, "Работа", "R1", Decimal("1"))],
        )

    def test_used_master_delete_is_friendly_and_safe(self):
        oid = self.saved_order()
        result = self.db.delete_employee(self.admin, self.master)
        self.assertEqual(result, "marked")
        self.assertTrue(self.db.is_soft_deleted("employee", self.master))
        self.assertTrue(any(int(r[0]) == self.master for r in self.db.get_employees(True)))
        self.assertFalse(any(int(r[0]) == self.master for r in self.db.get_active_employees(True)))
        self.assertIsNotNone(self.db.get_order(oid))

    def test_unused_worker_can_be_deleted(self):
        extra = self.db.add_employee(self.admin, "Удаляемый", False)
        result = self.db.delete_employee(self.admin, extra)
        self.assertEqual(result, "marked")
        self.assertTrue(self.db.is_soft_deleted("employee", extra))
        self.assertTrue(any(int(r[0]) == extra for r in self.db.get_employees(False)))

    def test_used_department_delete_is_friendly_and_safe(self):
        oid = self.saved_order()
        result = self.db.delete_department(self.admin, self.dep)
        self.assertEqual(result, "marked")
        self.assertTrue(self.db.is_soft_deleted("department", self.dep))
        self.assertFalse(any(int(r[0]) == self.dep for r in self.db.get_active_departments()))
        self.assertIsNotNone(self.db.get_order(oid))

    def test_unused_department_can_be_deleted(self):
        extra = self.db.add_department(self.admin, "Удаляемый цех")
        result = self.db.delete_department(self.admin, extra)
        self.assertEqual(result, "marked")
        self.assertTrue(self.db.is_soft_deleted("department", extra))
        self.assertTrue(any(int(r[0]) == extra for r in self.db.get_departments()))

    def test_work_only_and_employee_only_rows_both_survive(self):
        lines = [
            OrderLine(self.worker, "Работник", None, "", "", None),
            OrderLine(None, "", self.work, "Работа", "R1", Decimal("1")),
        ]
        oid = self.db.save_order(
            self.admin, "28-08-2026", "Дневная", self.master, self.dep, lines
        )
        loaded = self.db.get_order(oid)["lines"]
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].employee_name, "Работник")
        self.assertIsNone(loaded[0].work_type_id)
        self.assertEqual(loaded[1].work_name, "Работа")
        self.assertIsNone(loaded[1].employee_id)


if __name__ == "__main__":
    unittest.main()

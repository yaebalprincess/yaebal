import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

from smartorder.db import Database, DatabaseError
from smartorder.domain import OrderLine
from smartorder.security import Permission
from smartorder.excel import export_order_xlsx
import zipfile


class RC3SpecificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "work_orders.db")
        self.db.create_first_admin("admin", "password123")
        self.admin = self.db.authenticate("admin", "password123")
        self.master_id = self.db.add_employee(self.admin, "Мастер 1", True)
        self.worker_id = self.db.add_employee(self.admin, "Работник 1", False)
        self.dep_id = self.db.add_department(self.admin, "Студенты ночь")
        self.work_id = self.db.add_work_type(self.admin, "Фасовка", "TEST-001", "2.5")

    def tearDown(self):
        self.tmp.cleanup()

    def test_fix_and_fact_are_independent(self):
        line = OrderLine(
            self.worker_id, "Работник 1", self.work_id, "Фасовка", "TEST-001",
            Decimal("2.5"), fixed_boxes=Decimal("10"), fixed_weight=Decimal("3"),
            actual_value=Decimal("7"),
        )
        self.assertEqual(line.fixed_total, Decimal("30"))
        self.assertEqual(line.fixed_payment, Decimal("75.00"))
        self.assertEqual(line.actual_payment, Decimal("17.50"))

    def test_fixed_role_permissions(self):
        master = self.db.role_permissions("Мастер")
        accountant = self.db.role_permissions("Бухгалтер")
        self.assertIn(Permission.ORDERS_CREATE, master)
        self.assertIn(Permission.EMPLOYEES_EDIT, master)
        self.assertIn(Permission.BACKUP_MANAGE, master)
        self.assertIn(Permission.ADMIN_VIEW, master)
        self.assertNotIn(Permission.CATALOG_VIEW, master)
        self.assertIn(Permission.ORDERS_VIEW, accountant)
        self.assertIn(Permission.ORDERS_EXPORT, accountant)
        self.assertIn(Permission.CATALOG_VIEW, accountant)
        self.assertIn(Permission.CATALOG_CREATE, accountant)
        self.assertIn(Permission.CATALOG_EDIT, accountant)
        self.assertIn(Permission.CATALOG_DELETE, accountant)
        self.assertIn(Permission.CATALOG_IMPORT, accountant)
        self.assertIn(Permission.ADMIN_VIEW, accountant)
        self.assertIn(Permission.BACKUP_MANAGE, accountant)
        with self.assertRaises(DatabaseError):
            self.db.set_role_permissions(self.admin, "Бухгалтер", {Permission.ORDERS_CREATE})

    def test_date_range_filter(self):
        line = OrderLine(self.worker_id, "Работник 1", self.work_id, "Фасовка", "TEST-001", Decimal("2.5"), actual_value=Decimal("1"))
        self.db.save_order(self.admin, "26-08-2026", "Дневная", self.master_id, self.dep_id, [line])
        self.db.save_order(self.admin, "27-08-2026", "Дневная", self.master_id, self.dep_id, [line])
        self.db.save_order(self.admin, "28-08-2026", "Ночная", self.master_id, self.dep_id, [line])
        rows = self.db.list_orders(date_from="2026-08-27", date_to="2026-08-28")
        self.assertEqual({r[2] for r in rows}, {"27-08-2026", "28-08-2026"})
        night = self.db.list_orders(date_from="2026-08-26", date_to="2026-08-28", shift="Ночная")
        self.assertEqual(len(night), 1)
        self.assertEqual(night[0][2], "28-08-2026")

    def test_nomenclature_duplicate_is_friendly_and_batch_import_is_one_api(self):
        with self.assertRaisesRegex(DatabaseError, "уже существует"):
            self.db.add_work_type(self.admin, "Фасовка", "OTHER", "1")
        added, dup = self.db.import_work_types(self.admin, [
            ("Новая работа", "TEST-002", 3.0),
            ("Новая работа", "TEST-003", 4.0),
        ])
        self.assertEqual((added, dup), (1, 1))

    def test_special_department_excel_has_employee_subtotal(self):
        line1 = OrderLine(self.worker_id, "Работник 1", self.work_id, "Фасовка", "TEST-001", Decimal("2.5"), actual_value=Decimal("2"))
        second_work = self.db.add_work_type(self.admin, "Маркировка", "TEST-004", "1.5")
        line2 = OrderLine(self.worker_id, "Работник 1", second_work, "Маркировка", "TEST-004", Decimal("1.5"), fixed_boxes=Decimal("2"), fixed_weight=Decimal("3"))
        oid = self.db.save_order(self.admin, "28-08-2026", "Ночная", self.master_id, self.dep_id, [line1, line2])
        order = self.db.get_order(oid)
        target = Path(self.tmp.name) / "order.xlsx"
        export_order_xlsx(target, order)
        with zipfile.ZipFile(target, "r") as zf:
            sheet = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("ИТОГО по Работник 1:", sheet)
        self.assertIn("ИТОГО:", sheet)

    def test_backup_api_produces_readable_snapshot(self):
        target = Path(self.tmp.name) / "snapshot.db"
        self.db.backup_to(target)
        self.assertTrue(target.exists())
        rows = self.db.read_archive_orders(target)
        self.assertIsInstance(rows, list)

    def test_save_and_reload_both_payment_modes(self):
        line = OrderLine(
            self.worker_id, "Работник 1", self.work_id, "Фасовка", "TEST-001", Decimal("2.5"),
            fixed_boxes=Decimal("4"), fixed_weight=Decimal("2"), actual_value=Decimal("3"),
        )
        oid = self.db.save_order(self.admin, "28-08-2026", "Ночная", self.master_id, self.dep_id, [line])
        loaded = self.db.get_order(oid)["lines"][0]
        self.assertEqual(loaded.fixed_payment, Decimal("20.00"))
        self.assertEqual(loaded.actual_payment, Decimal("7.50"))


if __name__ == "__main__":
    unittest.main()

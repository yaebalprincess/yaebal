import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
import zipfile

from smartorder.db import Database, DatabaseError
from smartorder.domain import OrderLine, order_content_signature
from smartorder.excel import export_order_xlsx


class RC4SpecificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "work_orders.db")
        self.db.create_first_admin("admin", "password123")
        self.admin = self.db.authenticate("admin", "password123")
        self.master = self.db.add_employee(self.admin, "Мастер", True)
        self.worker = self.db.add_employee(self.admin, "Работник", False)
        self.dep = self.db.add_department(self.admin, "Обычный цех")
        self.work = self.db.add_work_type(self.admin, "Работа", "R-1", "2.5")

    def tearDown(self):
        self.tmp.cleanup()

    def line(self):
        return OrderLine(
            self.worker, "Работник", self.work, "Работа", "R-1", Decimal("2.5"),
            fixed_boxes=Decimal("123"), fixed_weight=Decimal("123"), actual_value=None,
        )

    def test_content_signature_ignores_derived_totals_and_is_stable(self):
        line = self.line()
        a = order_content_signature("28-08-2026", "Дневная", self.master, self.dep, [line], "Комментарий")
        # Merely reading derived values must not change business content.
        self.assertEqual(line.fixed_total, Decimal("15129"))
        self.assertEqual(line.fixed_payment, Decimal("37822.50"))
        b = order_content_signature("28-08-2026", "Дневная", self.master, self.dep, [line], "Комментарий")
        self.assertEqual(a, b)

    def test_content_signature_changes_only_when_business_content_changes(self):
        line = self.line()
        base = order_content_signature("28-08-2026", "Дневная", self.master, self.dep, [line], "Комментарий")
        same = OrderLine(**line.__dict__)
        self.assertEqual(base, order_content_signature("28-08-2026", "Дневная", self.master, self.dep, [same], "Комментарий"))
        changed = OrderLine(**line.__dict__); changed.fixed_boxes = Decimal("124")
        self.assertNotEqual(base, order_content_signature("28-08-2026", "Дневная", self.master, self.dep, [changed], "Комментарий"))

    def test_edit_revision_is_new_row_and_original_remains_unchanged(self):
        root = self.db.save_order(self.admin, "28-08-2026", "Дневная", self.master, self.dep, [self.line()], "A")
        edited_line = self.line(); edited_line.fixed_boxes = Decimal("124")
        rev = self.db.save_order(self.admin, "28-08-2026", "Дневная", self.master, self.dep, [edited_line], "B", parent_id=root)
        self.assertEqual(self.db.get_order(root)["info"]["version"], "1")
        self.assertEqual(self.db.get_order(rev)["info"]["version"], "1.1")
        self.assertEqual(self.db.get_order(root)["lines"][0].fixed_boxes, Decimal("123.0"))
        self.assertEqual(self.db.get_order(rev)["lines"][0].fixed_boxes, Decimal("124.0"))

    def test_roundtrip_manual_values_do_not_double(self):
        line = self.line()
        oid = self.db.save_order(self.admin, "28-08-2026", "Ночная", self.master, self.dep, [line])
        for _ in range(4):
            loaded = self.db.get_order(oid)["lines"][0]
            self.assertEqual(loaded.fixed_boxes, Decimal("123.0"))
            self.assertEqual(loaded.fixed_weight, Decimal("123.0"))
            self.assertEqual(loaded.fixed_total, Decimal("15129.00"))

    def test_delete_user_protects_current_user(self):
        self.db.add_user(self.admin, "master1", "password123", "Мастер")
        master_user = next(r for r in self.db.list_users() if r[1] == "master1")
        self.db.delete_user(self.admin, int(master_user[0]))
        self.assertFalse(any(r[1] == "master1" for r in self.db.list_users()))
        with self.assertRaises(DatabaseError):
            self.db.delete_user(self.admin, self.admin.id)

    def test_pieceworker_export_has_no_employee_subtotal(self):
        dep = self.db.add_department(self.admin, "Сдельный рабочий")
        second_work = self.db.add_work_type(self.admin, "Работа 2", "R-2", "1")
        lines = [
            self.line(),
            OrderLine(self.worker, "Работник", second_work, "Работа 2", "R-2", Decimal("1"), actual_value=Decimal("2")),
        ]
        oid = self.db.save_order(self.admin, "28-08-2026", "Дневная", self.master, dep, lines)
        target = Path(self.tmp.name) / "piece.xlsx"
        export_order_xlsx(target, self.db.get_order(oid))
        with zipfile.ZipFile(target) as zf:
            xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertNotIn("ИТОГО по Работник:", xml)
        self.assertIn("ИТОГО:", xml)

    def test_students_export_keeps_employee_subtotal(self):
        dep = self.db.add_department(self.admin, "Студенты ночь")
        oid = self.db.save_order(self.admin, "28-08-2026", "Ночная", self.master, dep, [self.line()])
        target = Path(self.tmp.name) / "students.xlsx"
        export_order_xlsx(target, self.db.get_order(oid))
        with zipfile.ZipFile(target) as zf:
            xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("ИТОГО по Работник:", xml)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from smartorder.db import Database


class LiteCoreTests(unittest.TestCase):
    def test_stable_ping(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "work_orders.db")
            self.assertGreater(db.stable_ping_ms(), 0)

    def test_shared_schema_has_core_tables(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "work_orders.db")
            with db.read_conn() as conn:
                names = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
            self.assertIn("work_orders", names)
            self.assertIn("work_order_layout_rows", names)

    def test_existing_v151_style_db_starts_without_optional_ddl(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "work_orders.db"
            first = Database(path)
            with first.write_conn() as conn:
                conn.execute("DELETE FROM db_meta WHERE key='smartorder_lite_schema'")
                conn.execute("DROP TABLE IF EXISTS role_permissions")
                conn.execute("DROP TABLE IF EXISTS permissions")
                conn.execute("DROP TABLE IF EXISTS work_order_edit_locks")
            second = Database(path)
            with second.read_conn() as conn:
                tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
                marker = conn.execute("SELECT value FROM db_meta WHERE key='smartorder_lite_schema'").fetchone()
            self.assertNotIn("role_permissions", tables)
            self.assertNotIn("permissions", tables)
            self.assertNotIn("work_order_edit_locks", tables)
            self.assertIsNone(marker)
            self.assertTrue(second.role_permissions("Администратор"))

if __name__ == "__main__":
    unittest.main()

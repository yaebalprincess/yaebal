import os
import tempfile
import unittest
from pathlib import Path

from smartorder.db import Database
from smartorder.security import SessionUser


class RC10StartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_local = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self.tmp.name
        self.db_path = Path(self.tmp.name) / "shared" / "work_orders.db"
        self.db = Database(self.db_path)

    def tearDown(self):
        if self.old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.old_local
        self.tmp.cleanup()

    def test_startup_bundle_primes_master_and_department_cache(self):
        admin = SessionUser(1, "admin", "Администратор", frozenset())
        # create records directly because permission checks are not the subject here
        with self.db.write_conn() as conn:
            conn.execute("INSERT INTO employees(name,is_master,registration_date) VALUES('Master A',1,'x')")
            conn.execute("INSERT INTO departments(name,registration_date) VALUES('Dept A','x')")
        self.db.invalidate_cache()
        has_users, enabled = self.db.startup_bundle()
        self.assertIsInstance(has_users, bool)
        self.assertIsInstance(enabled, bool)

        calls = {"count": 0}
        original = self.db._connect
        def counted(*a, **k):
            calls["count"] += 1
            return original(*a, **k)
        self.db._connect = counted
        self.assertEqual(self.db.get_employees(True)[0][1], "Master A")
        self.assertEqual(self.db.get_departments()[0][1], "Dept A")
        self.assertEqual(calls["count"], 0)

    def test_local_compat_marker_skips_full_schema_probe(self):
        # Fresh DB writes the local compatibility marker.
        marker = self.db._compat_marker_path()
        self.assertTrue(marker.exists())
        original = Database._legacy_schema_compatible
        try:
            def forbidden(self):
                raise AssertionError("full compatibility probe should not run")
            Database._legacy_schema_compatible = forbidden
            reopened = Database(self.db_path)
            self.assertTrue(reopened._legacy_compatible)
        finally:
            Database._legacy_schema_compatible = original

    def test_build_uses_native_launcher_not_pyinstaller_onefile(self):
        root = Path(__file__).resolve().parents[1]
        build = (root / "Build_SmartOrder.ps1").read_text(encoding="ascii")
        self.assertIn("csc.exe", build)
        self.assertIn("NativeLauncher.cs", build)
        self.assertNotIn('"--onefile"', build)
        native = (root / "NativeLauncher.cs").read_text(encoding="utf-8")
        self.assertNotIn("ABOVE_NORMAL", native)
        self.assertIn("SmartOrderApp.exe", native)

    def test_daily_shortcut_uses_local_native_launcher_with_updates(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "Install_and_Start_SmartOrder.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('$lnk.TargetPath=$LocalLauncher', text)
        self.assertIn('manifest.sha256', text)
        self.assertIn('Get-FileHash', text)
        self.assertNotIn('StartSmartOrderFast.vbs', text)
        self.assertNotIn('PriorityClass', text)


if __name__ == "__main__":
    unittest.main()

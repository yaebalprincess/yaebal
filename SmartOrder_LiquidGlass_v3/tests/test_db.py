import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

from smartorder.db import Database, StaleOrderError
from smartorder.domain import OrderLine

class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / 'work_orders.db')
        self.db.create_first_admin('admin', 'password123')
        self.user = self.db.authenticate('admin', 'password123')
        self.master = self.db.add_employee(self.user, 'Иванов И.И.', True)
        self.worker = self.db.add_employee(self.user, 'Петров П.П.', False)
        self.dep = self.db.add_department(self.user, 'Цех 1')
        self.work = self.db.add_work_type(self.user, 'Упаковка', 'ЗК-000220', '1.5')

    def tearDown(self):
        self.tmp.cleanup()

    def test_version_chain_and_snapshots(self):
        line = OrderLine(self.worker, 'Петров П.П.', self.work, 'Упаковка', 'ЗК-000220', Decimal('1.5'), Decimal('8'), Decimal('10'), Decimal('2'), None)
        first = self.db.save_order(self.user, '27-08-2026', 'Дневная', self.master, self.dep, [line])
        self.assertEqual(self.db.get_order(first)['info']['version'], '1')
        second = self.db.save_order(self.user, '27-08-2026', 'Дневная', self.master, self.dep, [line], parent_id=first)
        self.assertEqual(self.db.get_order(second)['info']['version'], '1.1')
        self.assertFalse(self.db.is_latest_order(first))
        self.assertTrue(self.db.is_latest_order(second))
        with self.assertRaises(StaleOrderError):
            self.db.save_order(self.user, '27-08-2026', 'Дневная', self.master, self.dep, [line], parent_id=first)
        loaded = self.db.get_order(second)['lines'][0]
        self.assertEqual(loaded.work_code, 'ЗК-000220')
        self.assertEqual(loaded.payment, Decimal('30.00'))

    def test_order_history(self):
        line = OrderLine(self.worker, 'Петров П.П.', self.work, 'Упаковка', 'ЗК-000220', Decimal('1.5'), actual_value=Decimal('2'))
        first = self.db.save_order(self.user, '27-08-2026', 'Дневная', self.master, self.dep, [line])
        second = self.db.save_order(self.user, '27-08-2026', 'Дневная', self.master, self.dep, [line], parent_id=first)
        hist = self.db.order_history(second)
        self.assertEqual([row['version'] for row in hist], ['1.1', '1'])

    def test_legacy_sha256_login_is_upgraded(self):
        import hashlib
        with self.db.write_conn() as conn:
            conn.execute("UPDATE users SET password_hash=? WHERE username='admin'", (hashlib.sha256(b'password123').hexdigest(),))
        user = self.db.authenticate('admin', 'password123')
        self.assertIsNotNone(user)
        with self.db.read_conn() as conn:
            stored = conn.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
        self.assertTrue(str(stored).startswith('scrypt$'))

    def test_lock(self):
        line = OrderLine(self.worker, 'Петров П.П.', self.work, 'Упаковка', 'ЗК-000220', Decimal('1.5'), actual_value=Decimal('2'))
        order = self.db.save_order(self.user, '27-08-2026', 'Дневная', self.master, self.dep, [line])
        token, owner = self.db.acquire_edit_lock(order, self.user)
        self.assertTrue(token)
        token2, owner2 = self.db.acquire_edit_lock(order, self.user)
        self.assertIsNone(token2)
        self.assertEqual(owner2['username'], 'admin')
        self.db.release_edit_lock(order, token)

if __name__ == '__main__':
    unittest.main()

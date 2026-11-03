import unittest
from decimal import Decimal
from smartorder.domain import OrderLine

class DomainTests(unittest.TestCase):
    def test_fixed_calculation(self):
        line = OrderLine(price=Decimal('1.5'), fixed_boxes=Decimal('10'), fixed_weight=Decimal('2.2'))
        self.assertEqual(line.fixed_total, Decimal('22.0'))
        self.assertEqual(line.payment, Decimal('33.00'))

    def test_fact_calculation(self):
        line = OrderLine(price=Decimal('10'), actual_value=Decimal('2.25'))
        self.assertEqual(line.payment, Decimal('22.50'))

if __name__ == '__main__':
    unittest.main()

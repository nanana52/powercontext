import unittest
from decimal import Decimal
from app.shipping import shipping_quote
class BoundaryTests(unittest.TestCase):
    def test_exact_100_standard_is_free(self):
        self.assertEqual(shipping_quote("100.00"),Decimal("0"))
    def test_exact_100_express_only_surcharge(self):
        self.assertEqual(shipping_quote("100.00","express"),Decimal("12"))

import unittest
from decimal import Decimal
from app.shipping import shipping_quote
class RegressionTests(unittest.TestCase):
    def test_below_threshold(self):
        self.assertEqual(shipping_quote("99.99"),Decimal("8"))
    def test_above_threshold(self):
        self.assertEqual(shipping_quote("100.01"),Decimal("0"))
    def test_express_below_threshold(self):
        self.assertEqual(shipping_quote("20","express"),Decimal("20"))
    def test_bad_method(self):
        with self.assertRaises(ValueError): shipping_quote("50","teleport")
    def test_negative(self):
        with self.assertRaises(ValueError): shipping_quote("-1")

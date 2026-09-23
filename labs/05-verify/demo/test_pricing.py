import unittest

from pricing import apply_discount, order_total


class PricingTest(unittest.TestCase):
    def test_discount_20_percent(self):
        self.assertAlmostEqual(apply_discount(100, 20), 80)

    def test_no_discount(self):
        self.assertAlmostEqual(apply_discount(59.9, 0), 59.9)

    def test_discount_out_of_range(self):
        with self.assertRaises(ValueError):
            apply_discount(100, 120)

    def test_order_total_counts_quantity(self):
        self.assertAlmostEqual(order_total([(10, 3), (2.5, 2)]), 35)


if __name__ == "__main__":
    unittest.main()

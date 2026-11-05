import unittest

from inventory import Inventory


class InventoryTests(unittest.TestCase):
    def test_rejects_insufficient_stock(self):
        inventory = Inventory(stock=2)
        with self.assertRaisesRegex(ValueError, "insufficient stock"):
            inventory.reserve(3)
        self.assertEqual(inventory.stock, 2)

    def test_reserves_available_stock(self):
        inventory = Inventory(stock=5)
        inventory.reserve(2)
        self.assertEqual(inventory.stock, 3)

    def test_reserves_exact_remaining_stock(self):
        inventory = Inventory(stock=2)
        inventory.reserve(2)
        self.assertEqual(inventory.stock, 0)


if __name__ == "__main__":
    unittest.main()

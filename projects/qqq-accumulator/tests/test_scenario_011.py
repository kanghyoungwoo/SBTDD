import unittest
from datetime import date
from decimal import Decimal

from src.app import DuplicateOrderError
from qqq_support import new_store


class TestStoreUniqueOrder(unittest.TestCase):
    def test_second_intent_for_same_day_and_rule_is_rejected(self):
        _root, store = new_store(self)
        day = date(2026, 11, 5)
        store.insert_order_intent(day, "le200", Decimal("4"), Decimal("102.00"), "SENDING")
        with self.assertRaises(DuplicateOrderError):
            store.insert_order_intent(
                day, "le200", Decimal("2"), Decimal("102.00"), "SENDING")
        rows = [o for o in store.list_orders()
                if o.trade_date == day and o.rule_id == "le200"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].quantity, Decimal("4"))


if __name__ == "__main__":
    unittest.main()

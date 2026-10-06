import json
import unittest
from pathlib import Path

from scripts.units import UnknownUnitError, factor_for, to_usd_per_ton

ROOT = Path(__file__).resolve().parent.parent


class TestUnitConversion(unittest.TestCase):
    def test_cents_per_pound(self):
        # 100 سنت بر پوند = 1 دلار بر پوند = 2204.6 دلار بر تن
        self.assertEqual(to_usd_per_ton(100, "U.S. Cents per Pound"), 2204.6)
        self.assertEqual(to_usd_per_ton(250.5, "U.S. Cents per Pound"), 5522.52)

    def test_dollars_per_metric_ton_unchanged(self):
        self.assertEqual(to_usd_per_ton(8123.45, "U.S. Dollars per Metric Ton"), 8123.45)

    def test_dollars_per_pound_and_kilogram(self):
        self.assertEqual(to_usd_per_ton(1, "U.S. Dollars per Pound"), 2204.6)
        self.assertEqual(to_usd_per_ton(2.5, "U.S. Dollars per Kilogram"), 2500.0)

    def test_unit_name_is_case_and_space_insensitive(self):
        self.assertEqual(factor_for("  u.s. CENTS   per pound "), 22.046)

    def test_unknown_unit_raises(self):
        with self.assertRaises(UnknownUnitError):
            to_usd_per_ton(10, "Index 2016=100")


class TestCommoditiesConfig(unittest.TestCase):
    def test_config_is_valid(self):
        items = json.loads((ROOT / "config" / "commodities.json").read_text(encoding="utf-8"))
        self.assertGreater(len(items), 0)
        ids = [c["fred_id"] for c in items]
        self.assertEqual(len(ids), len(set(ids)), "شناسه‌ی تکراری در فایل تنظیمات")
        for c in items:
            for field in ("fred_id", "name_fa", "name_en", "color"):
                self.assertTrue(c.get(field), f"فیلد {field} برای {c} خالی است")
            self.assertRegex(c["color"], r"^#[0-9A-Fa-f]{6}$")


if __name__ == "__main__":
    unittest.main()

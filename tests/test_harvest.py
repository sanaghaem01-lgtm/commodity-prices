import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestHarvestCalendar(unittest.TestCase):
    def test_calendar_is_valid(self):
        h = json.loads((ROOT / "config" / "harvest.json").read_text(encoding="utf-8"))
        groups = {c["category"] for c in json.loads((ROOT / "config" / "commodities.json").read_text(encoding="utf-8"))}
        self.assertTrue(h["rows"])
        for r in h["rows"]:
            self.assertIn(r["category"], groups, f"گروه ناشناخته: {r}")
            self.assertTrue(r["commodity"] and r["country"])
            main, second = r.get("main", []), r.get("second", [])
            self.assertTrue(main, f"ماه برداشت اصلی خالی است: {r}")
            for m in main + second:
                self.assertIn(m, range(1, 13), f"ماه نامعتبر: {r}")
            self.assertFalse(set(main) & set(second), f"یک ماه هم اصلی و هم دوم است: {r}")
        for s in h["sources"]:
            self.assertRegex(s["url"], r"^https://")


if __name__ == "__main__":
    unittest.main()

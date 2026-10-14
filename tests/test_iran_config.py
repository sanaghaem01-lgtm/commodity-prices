import json
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


class TestIranConfig(unittest.TestCase):
    def test_iran_commodities(self):
        items = load("iran_signals.json")["commodities"]
        keys = [c["key"] for c in items]
        self.assertEqual(len(keys), len(set(keys)))
        customs = {c["hs"] for c in load("iran_customs.json")["commodities"]}
        mirror = {c["hs"] for c in load("iran_imports.json")["commodities"]}
        for c in items:
            self.assertIn(c["customs_hs"], customs, c)
            if "mirror_hs" in c:
                self.assertIn(c["mirror_hs"], mirror, c)

    def test_demand_calendar(self):
        keys = {c["key"] for c in load("iran_signals.json")["commodities"]}
        for e in load("iran_demand.json")["events"]:
            self.assertLessEqual(date.fromisoformat(e["start"]), date.fromisoformat(e["end"]), e)
            self.assertTrue(set(e["commodities"]) <= keys, e)


if __name__ == "__main__":
    unittest.main()

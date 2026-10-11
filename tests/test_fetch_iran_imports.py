import json
import unittest
from datetime import date
from pathlib import Path

from scripts.fetch_iran_imports import build, months, tons_of

ROOT = Path(__file__).resolve().parent.parent
CONFIG = {
    "start": "2024-01",
    "commodities": [{"hs": "1006", "name_fa": "برنج", "fred_id": "PRICENPQUSDM", "note": ""}],
    "country_fa": {"India": "هند"},
}


def rec(**kw):
    base = {"cmdCode": "1006", "partnerCode": 364, "period": "202603", "reporterDesc": "India",
            "reporterCode": 699, "netWgt": 1_000_000.0, "primaryValue": 900_000.0}
    return {**base, **kw}


class TestIranImports(unittest.TestCase):
    def test_months_until_last_month(self):
        self.assertEqual(months("2025-11", today=date(2026, 2, 15)), ["202511", "202512", "202601"])

    def test_tons_from_weight_or_kg_quantity(self):
        self.assertEqual(tons_of({"netWgt": 2500.0}), 2.5)
        self.assertEqual(tons_of({"netWgt": None, "qty": 4000.0, "qtyUnitAbbr": "kg"}), 4.0)
        self.assertIsNone(tons_of({"netWgt": None, "qty": 10, "qtyUnitAbbr": "u"}))

    def test_build_filters_and_translates(self):
        records = [
            rec(),
            rec(reporterDesc="Oman", reporterCode=512, netWgt=None, primaryValue=500.0),
            rec(cmdCode="1801"),          # کالای دیگر
            rec(partnerCode=0),           # شریک دیگر
            rec(primaryValue=0),          # بدون ارزش
        ]
        data = build(CONFIG, records)
        rows = data["commodities"][0]["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"period": "2026-03", "country": "India", "country_fa": "هند",
                                   "tons": 1000.0, "usd": 900000})
        self.assertEqual(rows[1]["country_fa"], "Oman")  # بدون ترجمه، همان نام انگلیسی
        self.assertIsNone(rows[1]["tons"])

    def test_config_links_to_existing_commodities(self):
        cfg = json.loads((ROOT / "config" / "iran_imports.json").read_text(encoding="utf-8"))
        fred_ids = {c["fred_id"] for c in json.loads((ROOT / "config" / "commodities.json").read_text(encoding="utf-8"))}
        for c in cfg["commodities"]:
            self.assertIn(c["fred_id"], fred_ids)
            self.assertRegex(c["hs"], r"^\d{4,6}$")


if __name__ == "__main__":
    unittest.main()

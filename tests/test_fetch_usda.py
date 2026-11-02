import io
import json
import unittest
import zipfile
from pathlib import Path

from scripts.fetch_usda import build, read_rows, summarize

ROOT = Path(__file__).resolve().parent.parent
HEADER = "Commodity_Description,Country_Name,Market_Year,Calendar_Year,Month,Attribute_Description,Unit_Description,Value\n"


def line(com, country, year, attr, value, unit="(1000 MT)", cal="2026", month="10"):
    return f'"{com}","{country}",{year},{cal},{month},{attr},{unit},{value}\n'


def make_zip(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("psd.csv", text)
    return buf.getvalue()


CSV = HEADER + "".join([
    line("Corn", "Brazil", 2026, "Exports", 40000),
    line("Corn", "United States", 2026, "Exports", 60000),
    line("Corn", "Iran", 2026, "Imports", 8500),
    line("Corn", "China", 2026, "Imports", 10000),
    line("Corn", "Iran", 2026, "Domestic Consumption", 9850),
    line("Corn", "Iran", 2026, "Production", 1400),
    line("Corn", "Iran", 2025, "Imports", 9000),
    line("Corn", "Brazil", 2026, "Production", 100000),
    line("Corn", "Iran", 2026, "Yield", 7, unit="(MT/HA)"),   # شاخص نامربوط؛ حذف می‌شود
    line("Wheat", "Iran", 2026, "Imports", 2000),              # کالای نامربوط؛ حذف می‌شود
    line("Coffee, Green", "Iran", 2026, "Imports", 775, unit="(1000 60 KG BAGS)", month="7"),
    line("Coffee, Green", "Vietnam", 2026, "Exports", 1000, unit="(1000 60 KG BAGS)", month="7"),
])

CONFIG = {
    "seasons": 2, "top_n": 2,
    "commodities": [{"key": "corn", "name_fa": "ذرت", "psd": "Corn", "file": "grains_pulses"},
                    {"key": "coffee", "name_fa": "قهوه", "psd": "Coffee, Green", "file": "coffee"}],
    "country_fa": {"Brazil": "برزیل", "Iran": "ایران"},
}


class TestUsda(unittest.TestCase):
    def test_read_rows_filters(self):
        rows = read_rows(make_zip(CSV), {"Corn"})
        self.assertTrue(all(r["Commodity_Description"] == "Corn" for r in rows))
        self.assertFalse(any(r["Attribute_Description"] == "Yield" for r in rows))

    def test_summarize_world_iran_and_rankings(self):
        rows = read_rows(make_zip(CSV), {"Corn"})
        c = summarize(CONFIG["commodities"][0], rows, CONFIG)
        self.assertEqual(c["seasons"], [2025, 2026])
        self.assertEqual(c["release"], "2026-10")
        self.assertEqual(c["world"]["2026"]["exports"], 100000.0)
        self.assertEqual(c["iran"]["2026"]["imports"], 8500.0)
        self.assertEqual(c["iran"]["2025"]["imports"], 9000.0)
        self.assertEqual(c["iran_import_rank"], 2)                    # بعد از چین
        self.assertEqual(c["top_exporters"][0]["country"], "United States")   # بدون ترجمه، نام انگلیسی
        self.assertEqual(c["top_exporters"][1], {"country": "برزیل", "kt": 40000.0, "share": 40.0})

    def test_coffee_bags_become_thousand_tons(self):
        rows = read_rows(make_zip(CSV), {"Coffee, Green"})
        c = summarize(CONFIG["commodities"][1], rows, CONFIG)
        self.assertEqual(c["iran"]["2026"]["imports"], 46.5)          # 775 هزار کیسه‌ی 60 کیلویی
        self.assertEqual(c["release"], "2026-07")

    def test_unknown_unit_is_an_error_not_a_guess(self):
        bad = HEADER + line("Corn", "Iran", 2026, "Imports", 5, unit="(1000 BUSHELS)")
        data, errors = build({**CONFIG, "commodities": CONFIG["commodities"][:1]}, get=lambda name: make_zip(bad))
        self.assertEqual(data["commodities"], [])
        self.assertEqual(len(errors), 1)

    def test_download_failure_and_missing_commodity_are_reported(self):
        def get(name):
            raise RuntimeError("timeout")
        data, errors = build(CONFIG, get=get)
        self.assertEqual(len(errors), 2)
        data, errors = build(CONFIG, get=lambda name: make_zip(HEADER))
        self.assertEqual(len(errors), 2)

    def test_real_config_is_valid(self):
        cfg = json.loads((ROOT / "config" / "usda.json").read_text(encoding="utf-8"))
        keys = [c["key"] for c in cfg["commodities"]]
        self.assertEqual(len(keys), len(set(keys)))
        for c in cfg["commodities"]:
            self.assertIn(c["file"], ("oilseeds", "grains_pulses", "coffee"))


if __name__ == "__main__":
    unittest.main()

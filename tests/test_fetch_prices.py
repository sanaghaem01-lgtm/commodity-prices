import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.fetch_prices import build_dataset, has_changed, merge_with_existing, to_csv, validate, write_outputs
from scripts.fred_source import SourceError

CONFIG = [
    {"fred_id": "AAA", "name_fa": "الف", "name_en": "Alpha", "color": "#111111"},
    {"fred_id": "BBB", "name_fa": "ب", "name_en": "Beta", "color": "#222222"},
]
TODAY = date(2026, 10, 6)


def fake_fetch(data):
    def fetch(series_id, start):
        if isinstance(data[series_id], Exception):
            raise data[series_id]
        return data[series_id]
    return fetch


GOOD = {
    "AAA": {"unit": "U.S. Cents per Pound", "observations": [("2026-08-01", 100.0), ("2026-07-01", 90.0)]},
    "BBB": {"unit": "U.S. Dollars per Metric Ton", "observations": [("2026-08-01", 5000.0)]},
}


class TestFetchPrices(unittest.TestCase):
    def test_build_converts_and_sorts(self):
        ds, errors = build_dataset(CONFIG, fake_fetch(GOOD))
        self.assertEqual(errors, [])
        a = ds["commodities"][0]
        self.assertEqual([r["date"] for r in a["series"]], ["2026-07-01", "2026-08-01"])
        self.assertEqual(a["series"][-1]["usd_per_ton"], 2204.6)
        self.assertEqual(ds["commodities"][1]["series"][0]["usd_per_ton"], 5000.0)
        self.assertIsNone(a["tradingview_symbol"])  # فیلد اختیاری

    def test_optional_fields_passed_through(self):
        cfg = [{**CONFIG[0], "tradingview_symbol": "ICEUS:KC1!", "category": "غلات"}]
        ds, _ = build_dataset(cfg, fake_fetch(GOOD))
        self.assertEqual(ds["commodities"][0]["tradingview_symbol"], "ICEUS:KC1!")
        self.assertEqual(ds["commodities"][0]["category"], "غلات")

    def test_source_error_and_unknown_unit_are_reported(self):
        data = {"AAA": SourceError("HTTP 400 bad key"), "BBB": {"unit": "Index", "observations": [("2026-08-01", 1.0)]}}
        ds, errors = build_dataset(CONFIG, fake_fetch(data))
        self.assertEqual([sid for sid, _ in errors], ["AAA", "BBB"])
        self.assertEqual(ds["commodities"], [])

    def test_validate_empty_and_stale(self):
        data = {"AAA": {"unit": "U.S. Cents per Pound", "observations": []},
                "BBB": {"unit": "U.S. Dollars per Metric Ton", "observations": [("2025-01-01", 1.0)]}}
        ds, _ = build_dataset(CONFIG, fake_fetch(data))
        errors = validate(ds, None, today=TODAY)
        self.assertEqual(len(errors), 2)

    def test_validate_shrunk_or_older_than_existing(self):
        old, _ = build_dataset(CONFIG, fake_fetch(GOOD))
        shrunk = {**GOOD, "AAA": {"unit": "U.S. Cents per Pound", "observations": [("2026-07-01", 90.0)]}}
        new, _ = build_dataset(CONFIG, fake_fetch(shrunk))
        errors = validate(new, old, today=TODAY)
        self.assertEqual(len(errors), 2)  # هم عقب‌تر، هم کوتاه‌تر
        self.assertEqual(validate(old, old, today=TODAY), [])

    def test_merge_keeps_old_data_for_failed_commodity(self):
        old, _ = build_dataset(CONFIG, fake_fetch(GOOD))
        broken = {**GOOD, "AAA": SourceError("timeout"),
                  "BBB": {"unit": "U.S. Dollars per Metric Ton", "observations": [("2026-08-01", 5100.0)]}}
        new, errors = build_dataset(CONFIG, fake_fetch(broken))
        renamed = [{**CONFIG[0], "name_fa": "نام جدید"}, CONFIG[1]]
        merged = merge_with_existing(renamed, new, old, {sid for sid, _ in errors})
        a, b = merged["commodities"]
        self.assertEqual(a["series"], old["commodities"][0]["series"])  # داده‌ی قبلی حفظ شد
        self.assertEqual(a["name_fa"], "نام جدید")                       # ولی نام از تنظیمات فعلی
        self.assertEqual(b["series"][0]["usd_per_ton"], 5100.0)          # کالای سالم به‌روز شد

    def test_merge_drops_failed_new_commodity_and_follows_config_order(self):
        new, errors = build_dataset(CONFIG, fake_fetch({**GOOD, "AAA": SourceError("x")}))
        merged = merge_with_existing(list(reversed(CONFIG)), new, None, {sid for sid, _ in errors})
        self.assertEqual([c["fred_id"] for c in merged["commodities"]], ["BBB"])
        both, _ = build_dataset(CONFIG, fake_fetch(GOOD))
        merged = merge_with_existing(list(reversed(CONFIG)), both, None, set())
        self.assertEqual([c["fred_id"] for c in merged["commodities"]], ["BBB", "AAA"])

    def test_has_changed_ignores_last_updated(self):
        ds, _ = build_dataset(CONFIG, fake_fetch(GOOD))
        existing = {**ds, "last_updated": "2026-01-01T00:00:00Z"}
        self.assertFalse(has_changed(ds, existing))
        self.assertTrue(has_changed(ds, None))
        newer = {**GOOD, "BBB": {"unit": "U.S. Dollars per Metric Ton", "observations": [("2026-08-01", 5100.0)]}}
        ds2, _ = build_dataset(CONFIG, fake_fetch(newer))
        self.assertTrue(has_changed(ds2, existing))

    def test_csv_columns_and_write(self):
        ds, _ = build_dataset(CONFIG, fake_fetch(GOOD))
        lines = to_csv(ds).splitlines()
        self.assertEqual(lines[0], "date,commodity,price_original,unit_original,usd_per_ton")
        self.assertEqual(lines[1], "2026-07-01,Alpha,90.0,U.S. Cents per Pound,1984.14")
        with tempfile.TemporaryDirectory() as d:
            write_outputs(ds, d)
            self.assertEqual(json.loads((Path(d) / "prices.json").read_text(encoding="utf-8")), ds)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["prices.csv", "prices.json"])


if __name__ == "__main__":
    unittest.main()

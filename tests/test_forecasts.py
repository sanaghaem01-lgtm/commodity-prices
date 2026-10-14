import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestForecasts(unittest.TestCase):
    def test_forecasts_config(self):
        f = json.loads((ROOT / "config" / "forecasts.json").read_text(encoding="utf-8"))
        ids = {c["fred_id"] for c in json.loads((ROOT / "config" / "commodities.json").read_text(encoding="utf-8"))}
        self.assertRegex(f["url"], r"^https://")
        for fid, x in f["items"].items():
            self.assertIn(fid, ids, f"شناسه‌ی ناشناخته در پیش‌بینی‌ها: {fid}")
            for y in ("y2026", "y2027"):
                self.assertGreater(x[y], 0, fid)
            # پیش‌بینی بانک جهانی به دلار بر تن است؛ عدد خیلی کوچک یعنی تبدیل از دلار بر کیلو فراموش شده
            self.assertGreater(x["y2026"], 100, f"{fid}: واحد را بررسی کنید (دلار بر تن؟)")


if __name__ == "__main__":
    unittest.main()

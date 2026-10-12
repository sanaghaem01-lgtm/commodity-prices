import unittest
from datetime import datetime, timedelta, timezone

from scripts.fetch_iran_news import _pattern, merge, score

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
CONFIG = {
    "window_days": 7,
    "trade_words": ["گمرک", "واردات", "ثبت سفارش"],
    "commodity_words": ["ذرت", "مرغ", "دام", "جو", "گوشت"],
}


def item(title, hours_ago=1, source="الف", url=None):
    return {"title": title, "url": url or f"https://ex.ir/{abs(hash(title))}",
            "date": NOW - timedelta(hours=hours_ago), "source": source}


class TestIranNews(unittest.TestCase):
    def test_whole_word_matching(self):
        com = _pattern(CONFIG["commodity_words"])
        self.assertIsNone(com.search("منابع بانکی به کدام سو می‌روند"))   # «دام» داخل «کدام» نیست
        self.assertIsNone(com.search("پیش‌بینی وضعیت جوی امروز"))          # «جو» داخل «جوی» نیست
        self.assertIsNone(com.search("پایتخت؛ گل گوشتخوار سینما"))        # «گوشت» داخل «گوشتخوار» نیست
        self.assertIsNotNone(com.search("قیمت تخم‌مرغ در بازار"))          # نیم‌فاصله مرز کلمه است
        self.assertIsNotNone(com.search("واردات ذرت از برزیل"))

    def test_score(self):
        t, c = _pattern(CONFIG["trade_words"]), _pattern(CONFIG["commodity_words"])
        self.assertEqual(score("ترخیص ذرت از گمرک", t, c), 3)
        self.assertEqual(score("واردات خودرو آزاد شد", t, c), 2)
        self.assertEqual(score("قیمت مرغ کاهش یافت", t, c), 1)
        self.assertEqual(score("افتتاح نمایشگاه کتاب", t, c), 0)

    def test_merge_keeps_old_drops_expired_and_duplicates(self):
        old = [{**item("واردات ذرت افزایش یافت", hours_ago=30), "date": (NOW - timedelta(hours=30)).isoformat()},
               {**item("گمرک: ترخیص کالا سریع شد", hours_ago=24 * 9), "date": (NOW - timedelta(days=9)).isoformat()}]
        new = [item("واردات ذرت افزایش یافت", source="ب"),   # تکراری
               item("قیمت مرغ کاهش یافت"),
               item("افتتاح نمایشگاه کتاب")]                  # بی‌ربط
        out = merge(old, new, CONFIG, NOW)
        titles = [i["title"] for i in out]
        self.assertEqual(titles, ["واردات ذرت افزایش یافت", "قیمت مرغ کاهش یافت"])  # خبر ۹ روز پیش حذف شد
        self.assertEqual(out[0]["source"], "الف")  # نسخه‌ی قدیمی‌تر ماند



class TestShortageSignals(unittest.TestCase):
    SCONFIG = {
        "window_days": 120,
        "shortage_words": ["کمبود", "توقف ثبت سفارش", "افزایش قیمت"],
        "commodities": [
            {"key": "corn", "words": ["ذرت"]},
            {"key": "oil", "words": ["روغن"], "exclude": ["موتور"]},
        ],
    }

    def test_needs_both_commodity_and_shortage_word(self):
        from scripts.fetch_iran_news import merge_signals
        new = [item("کمبود ذرت دامی در بازار"),                 # هر دو ← نگه داشته می‌شود
               item("واردات ذرت از برزیل"),                     # بدون کلمه‌ی کمبود
               item("کمبود دارو در داروخانه‌ها"),               # بدون کالا
               item("افزایش قیمت روغن موتور"),                  # روغن موتور حذف می‌شود
               item("توقف ثبت سفارش روغن و ذرت")]               # دو کالا
        out = merge_signals([], new, self.SCONFIG, NOW)
        tags = {i["title"]: i["commodities"] for i in out}
        self.assertEqual(tags, {"کمبود ذرت دامی در بازار": ["corn"], "توقف ثبت سفارش روغن و ذرت": ["corn", "oil"]})

    def test_keeps_old_signals_within_window(self):
        from scripts.fetch_iran_news import merge_signals
        old = [{"title": "کمبود ذرت", "url": "https://ex.ir/1", "source": "الف",
                "date": (NOW - timedelta(days=60)).isoformat(), "commodities": ["corn"]},
               {"title": "کمبود روغن", "url": "https://ex.ir/2", "source": "الف",
                "date": (NOW - timedelta(days=200)).isoformat(), "commodities": ["oil"]}]
        out = merge_signals(old, [], self.SCONFIG, NOW)
        self.assertEqual([i["title"] for i in out], ["کمبود ذرت"])

    def test_signals_config_is_valid(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        s = json.loads((root / "config" / "iran_signals.json").read_text(encoding="utf-8"))
        keys = {c["key"] for c in s["commodities"]}
        self.assertEqual(len(keys), len(s["commodities"]))
        d = json.loads((root / "config" / "iran_demand.json").read_text(encoding="utf-8"))
        for e in d["events"]:
            start, end = datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])
            self.assertLessEqual(start, end, e)
            self.assertTrue(set(e["commodities"]) <= keys, e)


if __name__ == "__main__":
    unittest.main()

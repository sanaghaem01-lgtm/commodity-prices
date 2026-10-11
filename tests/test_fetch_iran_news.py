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


if __name__ == "__main__":
    unittest.main()

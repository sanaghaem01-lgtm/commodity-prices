import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.fetch_news import build, categorize, parse_feed

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Cocoa prices fall as &lt;b&gt;harvest&lt;/b&gt; improves</title><link>https://ex.com/a</link>
  <pubDate>Fri, 09 Oct 2026 08:00:00 +0000</pubDate><description>West Africa crop</description></item>
<item><title>New coffee shop opens</title><link>https://ex.com/b</link><pubDate>Sat, 10 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>Old wheat story</title><link>https://ex.com/c</link><pubDate>Mon, 01 Sep 2026 08:00:00 +0000</pubDate></item>
<item><title>Evil link about sugar</title><link>javascript:alert(1)</link><pubDate>Fri, 09 Oct 2026 08:00:00 +0000</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Wheat exports rise</title><link rel="self" href="https://ex.com/feed-self"/><link rel="alternate" href="https://ex.com/d"/>
  <updated>2026-10-08T10:00:00Z</updated><summary>Black Sea grain</summary></entry>
</feed>"""

CONFIG = {
    "window_days": 7, "per_category": 6,
    "sources": [{"name": "A", "url": "rss"}, {"name": "B", "url": "atom"}, {"name": "C", "url": "broken"}],
    "keywords": {"coffee-cocoa": ["coffee", "cocoa", "sugar"], "grains": ["wheat", "grain"]},
    "market_words": ["price", "prices", "harvest", "exports"],
    "reports": {"grains": [{"name": "IGC", "url": "https://www.igc.int/"}]},
}


def fake_fetch(url):
    if url == "broken":
        raise RuntimeError("timeout")
    return parse_feed(RSS if url == "rss" else ATOM)


class TestFetchNews(unittest.TestCase):
    def test_parse_rss_and_atom(self):
        rss = parse_feed(RSS)
        self.assertEqual(rss[0]["title"], "Cocoa prices fall as harvest improves")  # HTML پاک شد
        self.assertNotIn("javascript:alert(1)", [i["url"] for i in rss])         # لینک ناامن حذف شد
        atom = parse_feed(ATOM)
        self.assertEqual(atom[0]["url"], "https://ex.com/d")
        self.assertEqual(atom[0]["date"], datetime(2026, 10, 8, 10, tzinfo=timezone.utc))

    def test_build_categorizes_ranks_and_reports_errors(self):
        news, errors = build(CONFIG, fetch=fake_fetch, now=NOW)
        self.assertEqual(len(errors), 1)
        coffee = news["categories"]["coffee-cocoa"]
        # خبر بازاری (کاکائو) قبل از خبر جدیدتر ولی غیربازاری (کافی‌شاپ)
        self.assertEqual([i["url"] for i in coffee], ["https://ex.com/a", "https://ex.com/b"])
        grains = news["categories"]["grains"]
        self.assertEqual([i["url"] for i in grains], ["https://ex.com/d"])  # خبر قدیمی شهریور حذف شد
        self.assertEqual(grains[0]["source"], "B")
        self.assertEqual(news["reports"], CONFIG["reports"])

    def test_duplicates_removed(self):
        items = [{"title": f"Sugar price update {i % 2}", "url": f"https://ex.com/{i}", "summary": "",
                  "date": NOW, "source": f"S{i}"} for i in range(10)]
        cats = categorize(items, CONFIG, NOW)
        self.assertEqual(len(cats["coffee-cocoa"]), 2)  # فقط دو تیتر متفاوت

    def test_keyword_must_be_in_title(self):
        items = [{"title": "Top tips for farmers", "url": "https://ex.com/x", "summary": "wheat prices",
                  "date": NOW, "source": "A"}]
        self.assertEqual(categorize(items, CONFIG, NOW)["grains"], [])

    def test_max_two_per_source(self):
        items = [{"title": f"Sugar story {i}", "url": f"https://ex.com/{i}", "summary": "",
                  "date": NOW, "source": "A" if i < 5 else "B"} for i in range(8)]
        sources = [i["source"] for i in categorize(items, CONFIG, NOW)["coffee-cocoa"]]
        self.assertEqual(sorted(sources), ["A", "A", "B", "B"])

    def test_news_config_matches_commodity_groups(self):
        news_cfg = json.loads((ROOT / "config" / "news.json").read_text(encoding="utf-8"))
        commodities = json.loads((ROOT / "config" / "commodities.json").read_text(encoding="utf-8"))
        groups = {c["category"] for c in commodities}
        self.assertEqual(set(news_cfg["keywords"]), groups, "نام گروه‌ها در news.json با commodities.json یکی نیست")
        self.assertTrue(set(news_cfg["reports"]) - {"_همه"} <= groups)
        for src in news_cfg["sources"]:
            self.assertRegex(src["url"], r"^https://")


if __name__ == "__main__":
    unittest.main()

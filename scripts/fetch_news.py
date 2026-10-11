"""خواندن تیتر خبرهای هفته از خبرخوان‌های (RSS/Atom) سایت‌های تخصصی و ساختن data/news.json.

اجرا:  python3 -m scripts.fetch_news
فقط تیتر، نام منبع، تاریخ و لینک ذخیره می‌شود؛ متن خبر کپی نمی‌شود.

اگر چند منبع جواب ندهند، بقیه استفاده می‌شوند. اگر بیش از نیمی از منبع‌ها خطا بدهند،
فایل قبلی دست‌نخورده می‌ماند و برنامه با کد خطا تمام می‌شود.
"""

import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from scripts.fred_source import SSL_CONTEXT

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "news.json"
OUT_PATH = ROOT / "data" / "news.json"
USER_AGENT = "Mozilla/5.0 (compatible; commodity-prices-bot; +https://github.com/sanaghaem01-lgtm/commodity-prices)"
ATOM = "{http://www.w3.org/2005/Atom}"


# ---------- خواندن خبرخوان ----------

def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)  # قالب RSS
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))  # قالب Atom
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _clean(s):
    """حذف برچسب‌های HTML و فاصله‌های اضافه."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def parse_feed(xml_bytes):
    """خبرهای یک خبرخوان RSS یا Atom. خروجی: فهرست {title, url, date, summary}."""
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):  # RSS 2.0
        items.append({
            "title": _clean(_text(it.find("title"))),
            "url": _text(it.find("link")),
            "date": _parse_date(_text(it.find("pubDate"))),
            "summary": _clean(_text(it.find("description"))),
        })
    for it in root.iter(ATOM + "entry"):  # Atom
        link = it.find(ATOM + "link[@rel='alternate']")
        if link is None:
            link = it.find(ATOM + "link")
        items.append({
            "title": _clean(_text(it.find(ATOM + "title"))),
            "url": (link.get("href", "") if link is not None else "").strip(),
            "date": _parse_date(_text(it.find(ATOM + "published")) or _text(it.find(ATOM + "updated"))),
            "summary": _clean(_text(it.find(ATOM + "summary"))),
        })
    # فقط لینک‌های http(s)؛ هر چیز دیگری (مثلاً javascript:) کنار گذاشته می‌شود
    return [i for i in items if i["title"] and re.match(r"^https?://", i["url"])]


def fetch_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=25, context=SSL_CONTEXT) as resp:
                return parse_feed(resp.read())
        except Exception as e:  # شبکه یا XML خراب؛ یک بار دیگر امتحان کن
            last_error = e
            if attempt == 0:
                time.sleep(3)
    raise RuntimeError(f"{type(last_error).__name__}: {last_error}")


# ---------- دسته‌بندی ----------

def _pattern(words):
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)


MAX_PER_SOURCE = 2  # تا یک منبع پرکار، کل یک گروه را پر نکند


def categorize(items, config, now):
    """خبرهای چند روز اخیر را به گروه‌ها نسبت می‌دهد. یک خبر می‌تواند در چند گروه باشد.

    نام کالا باید در خود تیتر باشد. رتبه: اول خبرهایی که تیترشان به بازار مربوط است
    (قیمت، برداشت، صادرات…)، بعد آن‌هایی که خلاصه‌شان مربوط است، و در هر رده جدیدترها.
    """
    since = now - timedelta(days=config["window_days"])
    market = _pattern(config["market_words"])
    result = {}
    for cat, words in config["keywords"].items():
        kw = _pattern(words)
        candidates, seen = [], set()
        for it in items:
            if it["date"] is None or not (since <= it["date"] <= now + timedelta(days=1)):
                continue
            if not kw.search(it["title"]):
                continue
            key = re.sub(r"\W+", " ", it["title"].lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            score = 2 if market.search(it["title"]) else 1 if market.search(it["summary"]) else 0
            candidates.append((score, it["date"], it))
        candidates.sort(key=lambda p: (p[0], p[1]), reverse=True)

        picked, per_source = [], {}
        for _, _, it in candidates:
            if per_source.get(it["source"], 0) >= MAX_PER_SOURCE:
                continue
            per_source[it["source"]] = per_source.get(it["source"], 0) + 1
            picked.append({"title": it["title"], "url": it["url"], "source": it["source"],
                           "date": it["date"].strftime("%Y-%m-%d")})
            if len(picked) == config["per_category"]:
                break
        result[cat] = picked
    return result


# ---------- اجرا ----------

def build(config, fetch=fetch_feed, now=None):
    """خروجی: (news, errors)."""
    now = now or datetime.now(timezone.utc)
    items, errors = [], []
    for src in config["sources"]:
        try:
            for it in fetch(src["url"]):
                items.append({**it, "source": src["name"]})
        except Exception as e:
            errors.append(f"{src['name']}: {e}")
    news = {
        "window_days": config["window_days"],
        "categories": categorize(items, config, now),
        "reports": config.get("reports", {}),
    }
    return news, errors


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    news, errors = build(config)
    for e in errors:
        print("هشدار — این منبع جواب نداد: " + e, file=sys.stderr)

    if len(errors) > len(config["sources"]) / 2:
        print(f"خطا: {len(errors)} منبع از {len(config['sources'])} جواب ندادند؛ خبرهای قبلی دست‌نخورده ماند.", file=sys.stderr)
        return 1

    for cat, items in news["categories"].items():
        print(f"{cat}: {len(items)} خبر")

    old = json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else None
    if old is not None and {k: v for k, v in old.items() if k != "last_updated"} == news:
        print("خبرها تغییری نکرده‌اند؛ فایلی نوشته نشد.")
        return 0

    news["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(news, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, OUT_PATH)
    print("فایل data/news.json به‌روز شد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

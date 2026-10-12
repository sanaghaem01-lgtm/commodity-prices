"""جمع‌آوری تیتر خبرهای فارسی واردات، گمرک و کالاهای اساسی و ساختن data/iran-news.json.

اجرا:  python3 -m scripts.fetch_iran_news

خبرخوان‌های خبرگزاری‌های فارسی فقط چند ساعت اخیر را دارند، پس این برنامه هر چند ساعت یک بار اجرا می‌شود
و خبرهای جدید را به فهرست قبلی اضافه می‌کند؛ خبرهای قدیمی‌تر از چند روز حذف می‌شوند.
فقط تیتر، نام منبع، تاریخ و لینک ذخیره می‌شود.

همین برنامه «نشانه‌های کمبود» را هم جدا می‌کند: خبرهایی که هم نام یکی از کالاها و هم کلمه‌ای مثل
«کمبود» یا «توقف ثبت سفارش» دارند، در data/iran-signals.json و برای مدت طولانی‌تری نگه داشته می‌شوند.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.fetch_news import fetch_feed

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "iran_news.json"
OUT_PATH = ROOT / "data" / "iran-news.json"
SIGNALS_CONFIG_PATH = ROOT / "config" / "iran_signals.json"
SIGNALS_PATH = ROOT / "data" / "iran-signals.json"
MAX_STORED = 300


def _pattern(words):
    # \b در پایتون حروف فارسی را حرف حساب می‌کند؛ پس «دام» در «کدام» پیدا نمی‌شود
    words = sorted(words, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b")


def _key(title):
    return re.sub(r"\W+", " ", title).strip()


def score(title, trade, commodity):
    """۰ یعنی بی‌ربط. خبری که هم کالا و هم واردات/گمرک را دارد بالاتر است."""
    return 2 * bool(trade.search(title)) + bool(commodity.search(title))


def merge(old_items, new_items, config, now):
    """خبرهای قبلی + جدید، بدون تکرار، فقط چند روز اخیر، به ترتیب اهمیت و بعد تاریخ."""
    trade, commodity = _pattern(config["trade_words"]), _pattern(config["commodity_words"])
    since = now - timedelta(days=config["window_days"])
    by_key = {}
    for it in old_items + new_items:
        date = it["date"] if isinstance(it["date"], datetime) else datetime.fromisoformat(it["date"])
        if not (since <= date <= now + timedelta(days=1)):
            continue
        s = score(it["title"], trade, commodity)
        if s == 0:
            continue
        k = _key(it["title"])
        if k not in by_key:  # اولین نسخه (قدیمی‌تر) می‌ماند
            by_key[k] = {"title": it["title"], "url": it["url"], "source": it["source"],
                         "date": date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "score": s}
    items = sorted(by_key.values(), key=lambda i: (i["score"], i["date"]), reverse=True)
    return items[:MAX_STORED]


def _as_datetime(d):
    return d if isinstance(d, datetime) else datetime.fromisoformat(d)


def signal_tags(title, shortage, commodities):
    """کلیدهای کالاهایی که این تیتر درباره‌ی کمبود یا محدودیتشان است (یا فهرست خالی)."""
    if not shortage.search(title):
        return []
    keys = []
    for c in commodities:
        if c["words"].search(title) and not (c["exclude"] and c["exclude"].search(title)):
            keys.append(c["key"])
    return keys


def merge_signals(old_items, new_items, sconfig, now):
    """خبرهای کمبود قبلی + جدید، بدون تکرار، فقط چند ماه اخیر، جدیدترین اول."""
    shortage = _pattern(sconfig["shortage_words"])
    commodities = [{"key": c["key"], "words": _pattern(c["words"]),
                    "exclude": _pattern(c["exclude"]) if c.get("exclude") else None}
                   for c in sconfig["commodities"]]
    since = now - timedelta(days=sconfig["window_days"])
    by_key = {}
    for it in old_items + new_items:
        date = _as_datetime(it["date"])
        if not (since <= date <= now + timedelta(days=1)):
            continue
        tags = signal_tags(it["title"], shortage, commodities)
        k = _key(it["title"])
        if tags and k not in by_key:
            by_key[k] = {"title": it["title"], "url": it["url"], "source": it["source"],
                         "date": date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "commodities": tags}
    return sorted(by_key.values(), key=lambda i: i["date"], reverse=True)


def write_if_changed(path, payload, now, label):
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if {k: v for k, v in old.items() if k != "last_updated"} == payload:
        print(f"{label}: تغییری نکرده؛ فایلی نوشته نشد.")
        return
    payload = {**payload, "last_updated": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    print(f"{label}: فایل {path.relative_to(ROOT)} به‌روز شد.")


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    new_items, errors = [], []
    for src in config["sources"]:
        try:
            new_items += [{**it, "source": src["name"]} for it in fetch_feed(src["url"]) if it["date"]]
        except Exception as e:
            errors.append(f"{src['name']}: {e}")
    for e in errors:
        print("هشدار — این منبع جواب نداد: " + e, file=sys.stderr)
    if len(errors) > len(config["sources"]) / 2:
        print(f"خطا: {len(errors)} منبع از {len(config['sources'])} جواب ندادند؛ فایل قبلی دست‌نخورده ماند.", file=sys.stderr)
        return 1

    old = json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else {}
    items = merge(old.get("items", []), new_items, config, now)
    print(f"{len(items)} خبر مرتبط در {config['window_days']} روز اخیر.")
    write_if_changed(OUT_PATH, {"window_days": config["window_days"], "show": config["show"], "items": items},
                     now, "اخبار")

    sconfig = json.loads(SIGNALS_CONFIG_PATH.read_text(encoding="utf-8"))
    old_signals = json.loads(SIGNALS_PATH.read_text(encoding="utf-8")) if SIGNALS_PATH.exists() else {}
    signals = merge_signals(old_signals.get("items", []), new_items, sconfig, now)
    print(f"{len(signals)} خبر کمبود/محدودیت در {sconfig['window_days']} روز اخیر.")
    write_if_changed(SIGNALS_PATH, {"window_days": sconfig["window_days"], "items": signals}, now, "نشانه‌ها")
    return 0


if __name__ == "__main__":
    sys.exit(main())

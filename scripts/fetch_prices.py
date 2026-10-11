"""گرفتن قیمت کالاها، بررسی سلامت داده و ساختن data/prices.json و data/prices.csv.

اجرا:  python3 -m scripts.fetch_prices
کلید API فقط از متغیر محیطی FRED_API_KEY خوانده می‌شود.

اگر داده‌ی یک کالا خطا داشته باشد یا ناقص باشد، داده‌ی قبلیِ همان کالا حفظ می‌شود،
بقیه‌ی کالاها به‌روز می‌شوند و برنامه با کد خطا تمام می‌شود (تا workflow در GitHub قرمز شود).
"""

import csv
import io
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.units import UnknownUnitError, to_usd_per_ton

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "commodities.json"
DATA_DIR = ROOT / "data"
START_DATE = "2020-01-01"
SOURCE = "FRED (Federal Reserve Bank of St. Louis) / IMF Primary Commodity Prices"
MAX_STALE_DAYS = 180  # اگر آخرین داده‌ی یک کالا قدیمی‌تر از این باشد، احتمالاً سری متوقف شده
CSV_COLUMNS = ["date", "commodity", "price_original", "unit_original", "usd_per_ton"]


def load_config(path=CONFIG_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_existing(data_dir=DATA_DIR):
    path = Path(data_dir) / "prices.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def metadata(c):
    """اطلاعات نمایشی هر کالا، از فایل تنظیمات."""
    return {
        "fred_id": c["fred_id"],
        "category": c.get("category", ""),
        "name_fa": c["name_fa"],
        "name_en": c["name_en"],
        "color": c["color"],
        "tradingview_symbol": c.get("tradingview_symbol"),  # اختیاری؛ فقط برای لینک داشبورد
    }


def build_dataset(config, fetch_series, start=START_DATE):
    """داده‌ی همه‌ی کالاها را می‌گیرد. خروجی: (dataset, errors) و هر خطا به شکل (شناسه، پیام)."""
    commodities, errors = [], []
    for c in config:
        sid = c["fred_id"]
        try:
            result = fetch_series(sid, start)
            unit = result["unit"]
            series = [
                {"date": d, "price_original": v, "usd_per_ton": to_usd_per_ton(v, unit)}
                for d, v in sorted(result["observations"])
            ]
        except (UnknownUnitError, RuntimeError) as e:
            errors.append((sid, str(e)))
            continue
        commodities.append({**metadata(c), "unit_original": unit, "series": series})
    return {"source": SOURCE, "start_date": start, "commodities": commodities}, errors


def validate(dataset, existing, today=None):
    """بررسی کامل بودن داده‌ی جدید، در مقایسه با داده‌ی قبلی. خروجی: فهرست (شناسه، پیام)."""
    today = today or date.today()
    errors = []
    old = {c["fred_id"]: c for c in (existing or {}).get("commodities", [])}
    for c in dataset["commodities"]:
        sid, series = c["fred_id"], c["series"]
        if not series:
            errors.append((sid, "هیچ داده‌ای برنگشت"))
            continue
        latest = series[-1]["date"]
        age = (today - date.fromisoformat(latest)).days
        if age > MAX_STALE_DAYS:
            errors.append((sid, f"آخرین داده {latest} است ({age} روز پیش) — شاید سری متوقف شده"))
        if sid in old and old[sid]["series"]:
            old_series = old[sid]["series"]
            if latest < old_series[-1]["date"]:
                errors.append((sid, f"آخرین تاریخ ({latest}) از داده‌ی قبلی ({old_series[-1]['date']}) عقب‌تر است"))
            if len(series) < len(old_series):
                errors.append((sid, f"تعداد ماه‌ها از {len(old_series)} به {len(series)} کم شده"))
    return errors


def merge_with_existing(config, dataset, existing, bad_ids):
    """کالاهای سالم از داده‌ی جدید؛ کالاهای خطادار از داده‌ی قبلی (اگر بوده). ترتیب = فایل تنظیمات."""
    new = {c["fred_id"]: c for c in dataset["commodities"] if c["fred_id"] not in bad_ids}
    old = {c["fred_id"]: c for c in (existing or {}).get("commodities", [])}
    merged = []
    for c in config:
        sid = c["fred_id"]
        if sid in new:
            merged.append(new[sid])
        elif sid in old:
            # داده‌ی قبلی حفظ می‌شود، ولی نام/رنگ/گروه از تنظیمات فعلی می‌آید
            merged.append({**metadata(c), "unit_original": old[sid]["unit_original"], "series": old[sid]["series"]})
    return {**dataset, "commodities": merged}


def has_changed(dataset, existing):
    """آیا داده (بدون در نظر گرفتن تاریخ به‌روزرسانی) نسبت به قبل فرق کرده؟"""
    if existing is None:
        return True
    old = {k: v for k, v in existing.items() if k != "last_updated"}
    return old != dataset


def to_csv(dataset):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for c in dataset["commodities"]:
        for row in c["series"]:
            writer.writerow([row["date"], c["name_en"], row["price_original"], c["unit_original"], row["usd_per_ton"]])
    return buf.getvalue()


def write_outputs(dataset, data_dir=DATA_DIR):
    """هر دو فایل را اول موقت می‌نویسد و بعد جایگزین می‌کند، تا فایل نیمه‌کاره نماند."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    contents = {
        "prices.json": json.dumps(dataset, ensure_ascii=False, indent=1) + "\n",
        "prices.csv": to_csv(dataset),
    }
    for name, text in contents.items():
        (data_dir / (name + ".tmp")).write_text(text, encoding="utf-8")
    for name in contents:
        os.replace(data_dir / (name + ".tmp"), data_dir / name)


def main():
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        print("خطا: کلید FRED_API_KEY تعریف نشده است.", file=sys.stderr)
        return 1

    from scripts.fred_source import make_fetcher

    config = load_config()
    existing = load_existing()
    dataset, errors = build_dataset(config, make_fetcher(api_key))
    errors += validate(dataset, existing)
    bad_ids = {sid for sid, _ in errors}
    dataset = merge_with_existing(config, dataset, existing, bad_ids)

    if not dataset["commodities"]:
        print("خطا: داده‌ی هیچ کالایی در دسترس نیست؛ فایلی نوشته نشد.", file=sys.stderr)
        for sid, msg in errors:
            print(f"  - {sid}: {msg}", file=sys.stderr)
        return 1

    for c in dataset["commodities"]:
        last = c["series"][-1]
        flag = "  (داده‌ی قبلی حفظ شد)" if c["fred_id"] in bad_ids else ""
        print(f"{c['name_en']}: {len(c['series'])} ماه، آخرین: {last['date']} = {last['usd_per_ton']} USD/t ({c['unit_original']}){flag}")

    if has_changed(dataset, existing):
        dataset["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        write_outputs(dataset)
        print("فایل‌های data/prices.json و data/prices.csv به‌روز شدند.")
    else:
        print("داده نسبت به قبل تغییری نکرده؛ فایلی نوشته نشد.")

    if errors:
        print("این کالاها به‌روز نشدند (داده‌ی قبلی‌شان، اگر بود، دست‌نخورده ماند):", file=sys.stderr)
        for sid, msg in errors:
            print(f"  - {sid}: {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

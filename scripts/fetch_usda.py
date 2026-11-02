"""عرضه و تقاضای جهانی از پایگاه PSD وزارت کشاورزی آمریکا (USDA FAS) و ساختن data/usda.json.

اجرا:  python3 -m scripts.fetch_usda
فایل‌های CSV فشرده‌ی PSD عمومی‌اند و کلید لازم ندارند. USDA هر ماه بعد از گزارش WASDE به‌روزشان می‌کند.

عددها همه به «هزار تن» نگه داشته می‌شوند. فصل آخر پیش‌بینی خود USDA است، نه این سیستم.
اگر هر فایل یا کالایی خطا بدهد، فایل قبلی دست‌نخورده می‌ماند و برنامه با کد خطا تمام می‌شود.
"""

import csv
import io
import json
import os
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.fred_source import SSL_CONTEXT

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "usda.json"
OUT_PATH = ROOT / "data" / "usda.json"
URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_{}_csv.zip"
USER_AGENT = "Mozilla/5.0 (compatible; commodity-prices-bot; +https://github.com/sanaghaem01-lgtm/commodity-prices)"

ATTRS = {"Production": "production", "Domestic Consumption": "consumption", "Exports": "exports",
         "Imports": "imports", "Ending Stocks": "stocks"}
# ضریب تبدیل به هزار تن؛ واحد ناشناخته خطاست و حدس زده نمی‌شود
TO_KT = {"(1000 MT)": 1.0, "(1000 60 KG BAGS)": 0.06}


def download(name):
    req = urllib.request.Request(URL.format(name), headers={"User-Agent": USER_AGENT})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240, context=SSL_CONTEXT) as resp:
                return resp.read()
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"USDA ({name}): {last}")


def read_rows(zip_bytes, wanted):
    """ردیف‌های CSV داخل zip، فقط برای کالاهای خواسته‌شده و شاخص‌های لازم."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    with z.open(z.namelist()[0]) as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        return [r for r in reader if r["Commodity_Description"] in wanted and r["Attribute_Description"] in ATTRS]


def summarize(c, rows, config):
    """خلاصه‌ی یک کالا. خروجی: دیکشنری آماده‌ی نمایش."""
    fa = config.get("country_fa", {})
    rows = [r for r in rows if r["Commodity_Description"] == c["psd"]]
    if not rows:
        raise RuntimeError(f"USDA: برای «{c['psd']}» داده‌ای پیدا نشد")
    for r in rows:
        if r["Unit_Description"] not in TO_KT:
            raise RuntimeError(f"USDA: واحد ناشناخته‌ی {r['Unit_Description']} برای «{c['psd']}»")

    def value(r):
        return float(r["Value"]) * TO_KT[r["Unit_Description"]]

    latest = max(int(r["Market_Year"]) for r in rows)
    seasons = [latest - i for i in range(config["seasons"] - 1, -1, -1)]
    world = {str(s): {k: 0.0 for k in ATTRS.values()} for s in seasons}
    iran = {}
    for r in rows:
        s = int(r["Market_Year"])
        if s not in seasons:
            continue
        key = ATTRS[r["Attribute_Description"]]
        world[str(s)][key] += value(r)
        if r["Country_Name"] == "Iran":
            iran.setdefault(str(s), {})[key] = round(value(r), 1)

    def ranking(attr):
        vals = [(r["Country_Name"], value(r)) for r in rows
                if int(r["Market_Year"]) == latest and r["Attribute_Description"] == attr and value(r) > 0]
        vals.sort(key=lambda x: -x[1])
        total = sum(v for _, v in vals)
        top = [{"country": fa.get(n, n), "kt": round(v, 1), "share": round(v / total * 100, 1)}
               for n, v in vals[:config["top_n"]]]
        rank = next((i + 1 for i, (n, _) in enumerate(vals) if n == "Iran"), None)
        return top, rank

    exporters, _ = ranking("Exports")
    importers, iran_rank = ranking("Imports")
    release = max((r["Calendar_Year"], r["Month"].zfill(2)) for r in rows if int(r["Market_Year"]) == latest)
    return {
        "key": c["key"], "name_fa": c["name_fa"], "release": f"{release[0]}-{release[1]}",
        "seasons": seasons,
        "world": {s: {k: round(v, 1) for k, v in d.items()} for s, d in world.items()},
        "iran": iran, "iran_import_rank": iran_rank,
        "top_exporters": exporters, "top_importers": importers,
    }


def build(config, get=download):
    """خروجی: (data, errors)."""
    wanted = {c["psd"] for c in config["commodities"]}
    rows_by_file, commodities, errors = {}, [], []
    for name in sorted({c["file"] for c in config["commodities"]}):
        try:
            rows_by_file[name] = read_rows(get(name), wanted)
        except Exception as e:
            errors.append(str(e))
    for c in config["commodities"]:
        if c["file"] not in rows_by_file:
            continue
        try:
            commodities.append(summarize(c, rows_by_file[c["file"]], config))
        except RuntimeError as e:
            errors.append(str(e))
    return {"source": "USDA FAS — Production, Supply and Distribution (PSD)", "commodities": commodities}, errors


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data, errors = build(config)
    if errors:
        print("به‌روزرسانی انجام نشد؛ داده‌ی قبلی دست‌نخورده ماند. خطاها:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1
    for c in data["commodities"]:
        last = str(c["seasons"][-1])
        print(f"{c['name_fa']}: نسخه‌ی {c['release']}، فصل {last}، تولید جهانی {c['world'][last]['production']:,.0f} هزار تن، "
              f"واردات ایران {c['iran'].get(last, {}).get('imports', '—')}")

    old = json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else None
    if old is not None and {k: v for k, v in old.items() if k != "last_updated"} == data:
        print("داده تغییری نکرده؛ فایلی نوشته نشد.")
        return 0
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, OUT_PATH)
    print("فایل data/usda.json به‌روز شد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

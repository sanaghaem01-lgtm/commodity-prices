"""تبدیل فایل‌های Excel آمار واردات گمرک ایران به data/iran-customs.json.

اجرا:  python3 -m scripts.import_customs

سایت گمرک از سرورهای GitHub در دسترس نیست، پس این کار خودکار نیست: فایل تازه را از irica.ir بگیرید،
در پوشه‌ی private-data بگذارید و این برنامه را اجرا کنید. خود فایل‌های Excel وارد مخزن نمی‌شوند؛
فقط جمع‌بندی کالاهای config/iran_customs.json منتشر می‌شود. گزارش گمرک انتشار با ذکر منبع را مجاز می‌داند.

اگر سالی که قبلاً در خروجی بود حالا در فایل‌ها نباشد، یا یک سال در دو فایل بیاید،
چیزی نوشته نمی‌شود و برنامه با خطا تمام می‌شود.
"""

import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.worldbank_source import read_sheet

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "iran_customs.json"
OUT_PATH = ROOT / "data" / "iran-customs.json"
MONTH_WORDS = {"یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10, "یازده": 11}


def normalize(s):
    """یکسان کردن حروف عربی و فاصله‌ها، تا «عربي» و «عربی» یکی شوند."""
    s = str(s or "").replace("_x000D_", " ").replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("‌", " ")
    return " ".join(s.split())


def _number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_title(title):
    """«آمار واردات طی ده ماهه سال 1404» → 10؛ سال کامل → 12."""
    m = re.search(r"طی\s+(\S+)\s+ماهه", normalize(title))
    return MONTH_WORDS.get(m.group(1), 12) if m else 12


def find_table(rows):
    """شماره‌ی ردیف عنوان ستون‌ها و نقشه‌ی ستون‌ها؛ اگر این برگه جدول آمار نباشد None."""
    for i, r in enumerate(rows[:10]):
        cols = {normalize(v): c for c, v in r.items()}
        if "کدتعرفه" not in cols:
            continue
        pick = lambda word: next((c for name, c in cols.items() if word in name), None)
        return i, {"year": cols.get("سال"), "month": cols.get("ماه"), "customs": pick("گمرک"), "country": pick("کشور"),
                   "code": cols["کدتعرفه"], "desc": pick("شرح"), "kg": pick("وزن"), "usd": pick("دلار")}
    return None


def read_file(path):
    """جدول آمار یک فایل. خروجی: (ماه‌های دوره، ردیف‌ها)."""
    z = zipfile.ZipFile(path)
    names = re.findall(r'<sheet [^>]*name="([^"]+)"', z.read("xl/workbook.xml").decode("utf-8"))
    data = Path(path).read_bytes()
    for name in names:
        rows = read_sheet(data, name)
        found = find_table(rows)
        if not found:
            continue
        i, col = found
        title = " ".join(str(v) for r in rows[:i] for v in r.values())
        out = []
        for r in rows[i + 1:]:
            year = str(r.get(col["year"], "")).strip()
            if not year.isdigit():
                continue
            out.append({"year": int(year), "month": int(r[col["month"]]) if col["month"] is not None and str(r.get(col["month"], "")).isdigit() else None,
                        "customs": normalize(r.get(col["customs"])), "country": normalize(r.get(col["country"])),
                        "code": re.sub(r"\D", "", str(r.get(col["code"], ""))), "desc": normalize(r.get(col["desc"])),
                        "tons": _number(r.get(col["kg"])) / 1000, "usd": _number(r.get(col["usd"]))})
        return parse_title(title), out
    raise ValueError(f"جدول آمار در فایل «{Path(path).name}» پیدا نشد")


def _top(rows, key, limit):
    totals = {}
    for r in rows:
        k = r[key] if isinstance(key, str) else key(r)
        x = totals.setdefault(k, [0.0, 0.0])
        x[0] += r["tons"]
        x[1] += r["usd"]
    ranked = sorted(totals.items(), key=lambda kv: -kv[1][0])[:limit]
    return [{"name": k, "tons": round(v[0], 1), "usd": round(v[1])} for k, v in ranked]


def summarize(config, files):
    """files: فهرست (ماه‌های دوره، ردیف‌ها). هر سال باید فقط در یک فایل باشد."""
    periods, rows = {}, []
    for months, file_rows in files:
        for year in {r["year"] for r in file_rows}:
            if year in periods:
                raise ValueError(f"سال {year} در بیش از یک فایل آمده؛ فقط جدیدترین فایل همان سال را نگه دارید")
            periods[year] = months
        rows += file_rows
    commodities = []
    for c in config["commodities"]:
        mine = [r for r in rows if r["code"].startswith(c["hs"])]
        years, monthly = [], {}
        for year in sorted(periods):
            yr = [r for r in mine if r["year"] == year]
            years.append({
                "year": year, "months": periods[year], "partial": periods[year] < 12,
                "tons": round(sum(r["tons"] for r in yr), 1), "usd": round(sum(r["usd"] for r in yr)),
                "countries": _top(yr, "country", config["top_countries"]),
                "customs": _top(yr, "customs", config["top_customs"]),
                "codes": _top(yr, lambda r: f"{r['code']} — {r['desc']}", config["top_codes"]),
            })
            if any(r["month"] for r in yr):
                monthly[str(year)] = [round(sum(r["tons"] for r in yr if r["month"] == m), 1) for m in range(1, 13)]
        commodities.append({"hs": c["hs"], "name_fa": c["name_fa"], "years": years, "monthly": monthly})
    return {"source": "گمرک جمهوری اسلامی ایران (irica.ir)", "commodities": commodities}


def lost_years(new, old):
    """سال‌هایی که در خروجی قبلی بودند و حالا نیستند."""
    new_by = {c["hs"]: {y["year"] for y in c["years"]} for c in new["commodities"]}
    lost = []
    for c in (old or {}).get("commodities", []):
        if c["hs"] in new_by and "years" in c:
            lost += [f"{c['name_fa']} {y}" for y in sorted({y["year"] for y in c["years"]} - new_by[c["hs"]])]
    return lost


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    paths = sorted((ROOT / config["source_dir"]).rglob("*.xlsx"))
    if not paths:
        print(f"خطا: فایل Excel در پوشه‌ی {config['source_dir']} پیدا نشد.", file=sys.stderr)
        return 1
    try:
        files = [read_file(p) for p in paths]
        data = summarize(config, files)
    except ValueError as e:
        print(f"خطا: {e}", file=sys.stderr)
        return 1
    old = json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else None
    lost = lost_years(data, old)
    if lost:
        print("خطا: این سال‌ها قبلاً بودند ولی در فایل‌ها نیستند؛ چیزی نوشته نشد: " + "، ".join(lost), file=sys.stderr)
        return 1
    for c in data["commodities"]:
        print(c["name_fa"], {y["year"]: round(y["tons"]) for y in c["years"]})
    if old is not None and {k: v for k, v in old.items() if k != "last_updated"} == data:
        print("داده تغییری نکرده؛ فایلی نوشته نشد.")
        return 0
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, OUT_PATH)
    print("فایل data/iran-customs.json به‌روز شد. حالا باید commit و push شود.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""آمار واردات گمرک ایران از سامانه‌ی آمار اتاق بازرگانی تهران و ساختن data/iran-customs.json.

اجرا:  python3 -m scripts.fetch_iran_customs

برای هر کالا (۴ رقم اول کد تعرفه) و هر سال شمسی اخیر، فایل Excel جستجوی سایت گرفته می‌شود.
جستجوی سایت متنی است و ردیف‌های بی‌ربط هم برمی‌گرداند (مثلاً «1801» در شرح کالای دیگر)،
پس فقط ردیف‌هایی نگه داشته می‌شوند که کد تعرفه‌شان واقعاً با کد کالا شروع شود.

اگر درخواستی خطا بدهد، یا سالی که قبلاً داده داشت حالا خالی برگردد (یعنی احتمالاً سایت تغییر کرده)،
فایل قبلی دست‌نخورده می‌ماند و برنامه با کد خطا تمام می‌شود.
"""

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.fred_source import SSL_CONTEXT

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "iran_customs.json"
OUT_PATH = ROOT / "data" / "iran-customs.json"
URL = "https://service.tccim.ir/stats_TarrifCustomCountryDetail_excel"
USER_AGENT = "Mozilla/5.0 (compatible; commodity-prices-bot; +https://github.com/sanaghaem01-lgtm/commodity-prices)"


def persian_year(today=None):
    """سال شمسی جاری (تقریبی؛ نوروز ≈ ۲۱ مارس)."""
    today = today or date.today()
    return today.year - (621 if (today.month, today.day) >= (3, 21) else 622)


def normalize(s):
    """یکسان کردن حروف عربی و فاصله‌ها، تا «امارات متحده عربي» و «امارات متحده عربی» یکی شوند."""
    s = (s or "").replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("‌", " ")
    return " ".join(s.split())


def _number(s):
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_table(text, hs):
    """ردیف‌های جدول Excel (که در واقع HTML است) با کدی که با hs شروع می‌شود."""
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", text, re.S):
        cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                 for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        # ستون‌ها: ردیف، ماه، سال، گمرک، کشور، کد تعرفه، شرح، وزن (کیلو)، ارزش ریال، ارزش دلار
        if len(cells) < 10 or not cells[0].isdigit():
            continue
        code = re.sub(r"\D", "", cells[5])
        if not code.startswith(hs):
            continue
        rows.append({
            "year": int(cells[2]),
            "month": int(cells[1]) if cells[1].isdigit() else None,
            "customs": normalize(cells[3]),
            "country": normalize(cells[4]),
            "code": code,
            "desc": normalize(cells[6]),
            "tons": round(_number(cells[7]) / 1000, 3),
            "usd": round(_number(cells[9])),
        })
    return rows


def fetch(hs, year):
    params = {"mode": "doit", "slcImpExp": "Import", "slcCustom": "", "slcCountry": "",
              "sYear": year, "txtSearchWord": hs}
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params), headers={"User-Agent": USER_AGENT})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"اتاق تهران ({hs}، {year}): {last}")


def build(config, get=fetch, today=None):
    """خروجی: (data, errors)."""
    last_year = persian_year(today)
    years = list(range(last_year - config["years_back"], last_year + 1))
    commodities, errors = [], []
    for c in config["commodities"]:
        rows = []
        for y in years:
            try:
                rows += parse_table(get(c["hs"], y), c["hs"])
            except RuntimeError as e:
                errors.append(str(e))
            time.sleep(0 if get is not fetch else 2)  # با سایت مؤدب باشیم
        rows.sort(key=lambda r: (r["year"], r["month"] or 0, -r["usd"]))
        commodities.append({"hs": c["hs"], "name_fa": c["name_fa"], "rows": rows})
    return {"source": "گمرک ج.ا. ایران، از سامانه‌ی آمار اتاق بازرگانی تهران (service.tccim.ir)",
            "years": years, "commodities": commodities}, errors


def lost_years(new, old):
    """سال‌هایی که قبلاً داده داشتند و حالا خالی‌اند."""
    if not old:
        return []
    lost = []
    new_by = {c["hs"]: {r["year"] for r in c["rows"]} for c in new["commodities"]}
    for c in old.get("commodities", []):
        if c["hs"] not in new_by:
            continue
        for y in sorted({r["year"] for r in c["rows"]} - new_by[c["hs"]]):
            if y in new["years"]:
                lost.append(f"{c['name_fa']} {y}")
    return lost


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data, errors = build(config)
    old = json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else None
    lost = lost_years(data, old)
    if lost:
        errors.append("این سال‌ها قبلاً داده داشتند ولی حالا خالی برگشتند: " + "، ".join(lost))
    if errors:
        print("به‌روزرسانی انجام نشد؛ داده‌ی قبلی دست‌نخورده ماند. خطاها:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1

    for c in data["commodities"]:
        by_year = {}
        for r in c["rows"]:
            by_year[r["year"]] = by_year.get(r["year"], 0) + r["tons"]
        summary = "، ".join(f"{y}: {t:,.0f} تن" for y, t in sorted(by_year.items())) or "بدون داده"
        print(f"{c['name_fa']} ({c['hs']}): {summary}")

    if old is not None and {k: v for k, v in old.items() if k != "last_updated"} == data:
        print("داده تغییری نکرده؛ فایلی نوشته نشد.")
        return 0
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, OUT_PATH)
    print("فایل data/iran-customs.json به‌روز شد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

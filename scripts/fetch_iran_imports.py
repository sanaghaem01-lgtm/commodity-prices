"""آمار آینه‌ای واردات ایران از UN Comtrade و ساختن data/iran-imports.json.

«آینه‌ای» یعنی: کشورهای صادرکننده گزارش داده‌اند چه مقدار از هر کالا به ایران فروخته‌اند.
پوشش ناقص است (کشورهایی که گزارش نمی‌دهند یا از راه کشور واسطه می‌فروشند دیده نمی‌شوند).

اجرا:  python3 -m scripts.fetch_iran_imports
کلید از متغیر محیطی COMTRADE_API_KEY خوانده می‌شود. بدون کلید، از نسخه‌ی عمومی محدود
(هر درخواست یک ماه، کند) استفاده می‌شود که فقط برای آزمایش روی کامپیوتر خودمان است.

اگر هر درخواستی خطا بدهد، فایل قبلی دست‌نخورده می‌ماند و برنامه با کد خطا تمام می‌شود.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.fred_source import SSL_CONTEXT

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "iran_imports.json"
OUT_PATH = ROOT / "data" / "iran-imports.json"
IRAN = 364
DATA_URL = "https://comtradeapi.un.org/data/v1/get/C/M/HS"
PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"


def months(start, today=None):
    """ماه‌های start (مثلاً 2024-01) تا ماه قبل، به شکل 202401."""
    today = today or date.today()
    y, m = map(int, start.split("-"))
    out = []
    while (y, m) < (today.year, today.month):
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _get(url, params, api_key):
    full = url + "?" + urllib.parse.urlencode(params)
    headers = {"Ocp-Apim-Subscription-Key": api_key} if api_key else {}
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(full, headers=headers)
            with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("error"):
                raise RuntimeError(body["error"])
            return body.get("data") or []
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"   # کلید در آدرس نیست، پس چاپ خطا امن است
            if e.code in (401, 403):
                break                 # کلید اشتباه؛ تکرار فایده ندارد
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(5 * (attempt + 1))  # سرور گاهی موقتاً محدود می‌کند
    raise RuntimeError(f"Comtrade ({params.get('period')}): {last}")


def fetch_records(hs_codes, periods, api_key):
    """رکوردهای خام: صادرات همه‌ی کشورها به ایران برای این کدها و ماه‌ها."""
    batch = 12 if api_key else 1  # نسخه‌ی عمومی هر بار فقط یک ماه
    url = DATA_URL if api_key else PREVIEW_URL
    records = []
    for i in range(0, len(periods), batch):
        params = {
            "partnerCode": IRAN, "flowCode": "X", "cmdCode": ",".join(hs_codes),
            "period": ",".join(periods[i:i + batch]), "includeDesc": "true",
            # فقط جمع کل (نه تفکیک به نوع حمل یا رویه‌ی گمرکی) تا چیزی دوبار شمرده نشود
            "motCode": 0, "customsCode": "C00", "partner2Code": 0,
        }
        records += _get(url, params, api_key)
        time.sleep(1 if api_key else 3)
    return records


def tons_of(r):
    if r.get("netWgt"):
        return r["netWgt"] / 1000
    if r.get("qty") and (r.get("qtyUnitAbbr") or "").lower() == "kg":
        return r["qty"] / 1000
    return None  # وزن گزارش نشده؛ ارزش هست ولی قیمت هر تن قابل محاسبه نیست


def build(config, records):
    by_hs = {c["hs"]: [] for c in config["commodities"]}
    for r in records:
        hs = str(r.get("cmdCode"))
        if hs not in by_hs or r.get("partnerCode") != IRAN or not r.get("primaryValue"):
            continue
        p = str(r["period"])
        name = r.get("reporterDesc") or str(r.get("reporterCode"))
        t = tons_of(r)
        by_hs[hs].append({
            "period": f"{p[:4]}-{p[4:6]}",
            "country": name,
            "country_fa": config.get("country_fa", {}).get(name, name),
            "tons": round(t, 1) if t is not None else None,
            "usd": round(r["primaryValue"]),
        })
    commodities = []
    for c in config["commodities"]:
        rows = sorted(by_hs[c["hs"]], key=lambda x: (x["period"], -x["usd"]))
        commodities.append({**{k: c[k] for k in ("hs", "name_fa", "fred_id", "note")}, "rows": rows})
    return {
        "source": "UN Comtrade — صادرات گزارش‌شده‌ی کشورها به ایران (آمار آینه‌ای)",
        "start": config["start"],
        "commodities": commodities,
    }


def main():
    api_key = os.environ.get("COMTRADE_API_KEY", "").strip()
    if not api_key:
        print("هشدار: COMTRADE_API_KEY تعریف نشده؛ از نسخه‌ی عمومی محدود استفاده می‌شود (کند).", file=sys.stderr)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    periods = months(config["start"])
    try:
        records = fetch_records([c["hs"] for c in config["commodities"]], periods, api_key)
    except RuntimeError as e:
        print(f"خطا: {e}\nداده‌ی قبلی دست‌نخورده ماند.", file=sys.stderr)
        return 1

    data = build(config, records)
    total = sum(len(c["rows"]) for c in data["commodities"])
    if total == 0:
        print("خطا: هیچ رکوردی برنگشت؛ داده‌ی قبلی دست‌نخورده ماند.", file=sys.stderr)
        return 1
    for c in data["commodities"]:
        last = max((r["period"] for r in c["rows"]), default="—")
        print(f"{c['name_fa']} ({c['hs']}): {len(c['rows'])} رکورد، آخرین ماه: {last}")

    old = json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else None
    if old is not None and {k: v for k, v in old.items() if k != "last_updated"} == data:
        print("داده تغییری نکرده؛ فایلی نوشته نشد.")
        return 0
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, OUT_PATH)
    print("فایل data/iran-imports.json به‌روز شد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

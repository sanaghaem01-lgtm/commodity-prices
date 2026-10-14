"""گرفتن قیمت ماهانه‌ی کالا از «Pink Sheet» بانک جهانی (فایل Excel ماهانه، مجوز CC BY 4.0).

خروجی هم‌شکل fred_source است تا fetch_prices هر دو را یکسان استفاده کند:
    fetch_series(column, start) -> {"unit": str, "observations": [(date, value), ...]}

آدرس فایل Excel هر ماه کمی عوض می‌شود، پس هر بار از صفحه‌ی بانک جهانی پیدا می‌شود.
فایل xlsx با کتابخانه‌ی استاندارد پایتون (zipfile) خوانده می‌شود؛ کتابخانه‌ی اضافه لازم نیست.
"""

import io
import re
import time
import urllib.request
import zipfile

from scripts.fred_source import SSL_CONTEXT, SourceError

PAGE_URL = "https://www.worldbank.org/en/research/commodity-markets"
FILE_PATTERN = r'href="(https://[^"]+/CMO-Historical-Data-Monthly\.xlsx)"'
SHEET = "Monthly Prices"
USER_AGENT = "Mozilla/5.0 (compatible; commodity-prices-bot; +https://github.com/sanaghaem01-lgtm/commodity-prices)"

# واحدهای فایل بانک جهانی → نام واحد به همان شکلی که units.py می‌شناسد
UNITS = {
    "($/kg)": "U.S. Dollars per Kilogram",
    "($/mt)": "U.S. Dollars per Metric Ton",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90, context=SSL_CONTEXT) as resp:
                return resp.read()
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(5 * (attempt + 1))
    raise SourceError(f"بانک جهانی ({url}): {last}")


def find_file_url(page_html):
    m = re.search(FILE_PATTERN, page_html)
    if not m:
        raise SourceError("بانک جهانی: لینک فایل CMO-Historical-Data-Monthly.xlsx در صفحه پیدا نشد (شاید صفحه عوض شده)")
    return m.group(1)


# ---------- خواندن xlsx ----------

def _col_index(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_sheet(xlsx_bytes, sheet_name=SHEET):
    """ردیف‌های یک برگه، هر ردیف یک دیکشنری {شماره‌ی ستون: مقدار متنی}."""
    z = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    wb = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    m = re.search(r'<sheet [^>]*name="%s"[^>]*r:id="(rId\d+)"' % re.escape(sheet_name), wb)
    if not m:
        raise SourceError(f"بانک جهانی: برگه‌ی «{sheet_name}» در فایل نیست")
    rel = re.search(r'<Relationship [^>]*Id="%s"[^>]*Target="([^"]+)"' % m.group(1), rels) or \
        re.search(r'<Relationship [^>]*Target="([^"]+)"[^>]*Id="%s"' % m.group(1), rels)
    target = rel.group(1).lstrip("/")
    target = target if target.startswith("xl/") else "xl/" + target

    strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss = z.read("xl/sharedStrings.xml").decode("utf-8")
        strings = ["".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)) for si in re.findall(r"<si>(.*?)</si>", ss, re.S)]

    rows = []
    for row in re.findall(r"<row [^>]*>(.*?)</row>", z.read(target).decode("utf-8"), re.S):
        cells = {}
        for ref, attrs, body in re.findall(r'<c r="([A-Z]+\d+)"([^>]*)>(.*?)</c>', row, re.S):
            v = re.search(r"<v>(.*?)</v>", body)
            if v:
                cells[_col_index(ref)] = strings[int(v.group(1))] if 't="s"' in attrs else v.group(1)
            else:
                t = re.search(r"<t[^>]*>(.*?)</t>", body, re.S)  # رشته‌ی درون‌خطی
                if t:
                    cells[_col_index(ref)] = t.group(1)
        rows.append(cells)
    return rows


def _clean(name):
    """«Beef **» → «beef»؛ تا علامت‌های پانویس روی تطبیق نام ستون اثر نگذارند."""
    return " ".join(name.replace("*", " ").split()).lower()


def parse_prices(rows):
    """خروجی: {نام ستون تمیزشده: (واحد، [(تاریخ، مقدار)])}."""
    header = next((i for i, r in enumerate(rows) if any(_clean(str(v)) == "cocoa" for v in r.values())), None)
    if header is None or header + 1 >= len(rows):
        raise SourceError("بانک جهانی: ردیف عنوان ستون‌ها پیدا نشد (شاید ساختار فایل عوض شده)")
    names, units = rows[header], rows[header + 1]
    out = {}
    for col, name in names.items():
        series = []
        for r in rows[header + 2:]:
            period = str(r.get(0, ""))
            m = re.fullmatch(r"(\d{4})M(\d{2})", period)
            if not m:
                continue
            try:
                series.append((f"{m.group(1)}-{m.group(2)}-01", float(r[col])))
            except (KeyError, ValueError):
                continue  # «…» یعنی داده نیست
        out[_clean(name)] = (units.get(col, ""), series)
    return out


def make_fetcher(get=_get):
    """تابع fetch_series که فایل را فقط یک بار دانلود می‌کند."""
    cache = {}

    def fetch_series(column, start):
        if "prices" not in cache:
            url = find_file_url(get(PAGE_URL).decode("utf-8", errors="replace"))
            cache["prices"] = parse_prices(read_sheet(get(url)))
        prices = cache["prices"]
        key = _clean(column)
        if key not in prices:
            raise SourceError(f"بانک جهانی: ستون «{column}» در فایل نیست")
        unit_text, series = prices[key]
        if unit_text not in UNITS:
            raise SourceError(f"بانک جهانی: واحد ناشناخته‌ی «{unit_text}» برای «{column}»")
        return {"unit": UNITS[unit_text], "observations": [(d, v) for d, v in series if d >= start]}

    return fetch_series

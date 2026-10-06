"""گرفتن داده از API رسمی FRED.

این تنها فایلی است که به منبع داده وابسته است. اگر روزی منبع عوض شد
(مثلاً سرویس روزانه‌ی پولی)، فقط باید فایلی با همین خروجی ساخت:
    fetch_series(series_id, start) -> {"unit": str, "observations": [(date, value), ...]}
"""

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.stlouisfed.org/fred"
RETRIES = 3


def _ssl_context():
    # پایتونِ نصب‌شده از python.org روی مک گواهی‌های سیستم را نمی‌بیند؛
    # اگر بسته‌ی certifi موجود باشد از آن استفاده می‌کنیم، وگرنه پیش‌فرض سیستم.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


SSL_CONTEXT = _ssl_context()


class SourceError(RuntimeError):
    """خطا در گرفتن داده از منبع."""


def _get(endpoint, params, api_key):
    query = urllib.parse.urlencode({**params, "api_key": api_key, "file_type": "json"})
    url = f"{BASE_URL}/{endpoint}?{query}"
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=30, context=SSL_CONTEXT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # پیام خطای FRED را بخوان؛ خود URL را (که کلید دارد) هرگز چاپ نکن
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error_message", "")
            except Exception:
                detail = ""
            last_error = f"HTTP {e.code} {detail}".strip()
            if e.code < 500 and e.code != 429:
                break  # خطای درخواست (مثلاً کلید اشتباه)؛ تکرار فایده ندارد
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_error = type(e).__name__ + ": " + str(getattr(e, "reason", e))
        if attempt < RETRIES:
            time.sleep(2 * attempt)
    raise SourceError(f"FRED /{endpoint} ({params.get('series_id')}): {last_error}")


def make_fetcher(api_key):
    """یک تابع fetch_series می‌سازد که کلید را در خود نگه می‌دارد."""

    def fetch_series(series_id, start):
        meta = _get("series", {"series_id": series_id}, api_key)
        series = meta.get("seriess") or []
        if not series or not series[0].get("units"):
            raise SourceError(f"FRED: واحد سری {series_id} برگردانده نشد")

        data = _get(
            "series/observations",
            {"series_id": series_id, "observation_start": start},
            api_key,
        )
        observations = []
        for obs in data.get("observations", []):
            if obs.get("value") in (None, "", "."):  # «.» یعنی FRED برای این ماه مقدار ندارد
                continue
            try:
                observations.append((obs["date"], float(obs["value"])))
            except (KeyError, ValueError):
                raise SourceError(f"FRED: مقدار نامعتبر در سری {series_id}: {obs!r}")

        return {"unit": series[0]["units"], "observations": observations}

    return fetch_series

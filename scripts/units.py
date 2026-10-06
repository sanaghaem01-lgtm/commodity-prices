"""تبدیل واحدهای قیمت به «دلار بر تن متریک» (USD/t).

واحد هر سری از خود FRED خوانده می‌شود و این‌جا به ضریب تبدیل نگاشت می‌شود.
اگر واحدی ناشناخته باشد، حدس زده نمی‌شود و خطا داده می‌شود.
"""

# ۱ تن متریک = 2204.6 پوند  →  سنت بر پوند × 22.046 = دلار بر تن
CENTS_PER_LB_TO_USD_PER_TON = 22.046

# کلیدها: نام واحد به همان شکلی که FRED برمی‌گرداند (با حروف کوچک)
FACTORS = {
    "u.s. cents per pound": CENTS_PER_LB_TO_USD_PER_TON,
    "u.s. dollars per pound": CENTS_PER_LB_TO_USD_PER_TON * 100,
    "u.s. dollars per metric ton": 1.0,
    "u.s. dollars per kilogram": 1000.0,
}


class UnknownUnitError(ValueError):
    """واحدی که تبدیلش را نمی‌دانیم."""


def _normalize(unit):
    return " ".join(unit.strip().lower().split())


def factor_for(unit):
    """ضریب تبدیل واحد داده‌شده به دلار بر تن."""
    key = _normalize(unit)
    if key not in FACTORS:
        raise UnknownUnitError(
            f"واحد ناشناخته از منبع داده: {unit!r}. "
            f"تبدیل این واحد باید در scripts/units.py تعریف شود."
        )
    return FACTORS[key]


def to_usd_per_ton(value, unit):
    """تبدیل یک قیمت به دلار بر تن، گرد شده تا ۲ رقم اعشار."""
    return round(value * factor_for(unit), 2)

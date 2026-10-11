import unittest
from datetime import date

from scripts.fetch_iran_customs import build, lost_years, normalize, parse_table, persian_year

TABLE = """<table>
<tr><td>آمار واردات سال 1402</td></tr>
<tr><th>ردیف</th><th>ماه</th><th>سال</th><th>نام گمرک</th><th>نام کشور</th><th>شماره تعرفه</th>
<th>توضیحات تعرفه</th><th>وزن - کیلو گرم</th><th>ارزش - ریال</th><th>ارزش - دلار</th></tr>
<tr><td>1</td><td>8</td><td>1402</td><td>بندر امام خميني</td><td>امارات متحده عربي</td><td>1801 0090</td>
<td>دانه کاکائو</td><td>2,500,000</td><td>1,000</td><td>8,750,000</td></tr>
<tr><td>2</td><td></td><td>1402</td><td>تهران</td><td>ترکيه</td><td>84819040</td>
<td>اجزاء شيرالات مشمول ردیف 1801</td><td>10</td><td>1</td><td>50</td></tr>
<tr><td></td><td>مجموع کل 1,001 ریال</td><td>مجموع کل 8,750,050 دلار</td></tr>
</table>"""


class TestIranCustoms(unittest.TestCase):
    def test_persian_year(self):
        self.assertEqual(persian_year(date(2026, 10, 11)), 1405)
        self.assertEqual(persian_year(date(2026, 3, 1)), 1404)

    def test_normalize_arabic_letters(self):
        self.assertEqual(normalize("امارات متحده عربي"), "امارات متحده عربی")
        self.assertEqual(normalize("ترکيه  "), "ترکیه")
        self.assertEqual(normalize("كنجاله"), "کنجاله")

    def test_parse_keeps_only_matching_codes(self):
        rows = parse_table(TABLE, "1801")
        self.assertEqual(len(rows), 1)  # شیرآلات با «1801» در شرح حذف شد؛ سطر جمع کل هم
        self.assertEqual(rows[0], {"year": 1402, "month": 8, "customs": "بندر امام خمینی",
                                   "country": "امارات متحده عربی", "code": "18010090",
                                   "desc": "دانه کاکائو", "tons": 2500.0, "usd": 8750000})

    def test_build_reports_errors_and_lost_years(self):
        def get(hs, year):
            if year == 1404:
                raise RuntimeError("timeout")
            return TABLE if year == 1402 else "<table></table>"
        cfg = {"years_back": 2, "commodities": [{"hs": "1801", "name_fa": "کاکائو"}]}
        data, errors = build(cfg, get=get, today=date(2026, 10, 11))
        self.assertEqual(data["years"], [1403, 1404, 1405])
        self.assertEqual(len(errors), 1)
        old = {"commodities": [{"hs": "1801", "name_fa": "کاکائو", "rows": [{"year": 1403}]}]}
        self.assertEqual(lost_years(data, old), ["کاکائو 1403"])
        self.assertEqual(lost_years(data, None), [])


if __name__ == "__main__":
    unittest.main()

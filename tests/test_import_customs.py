import unittest

from scripts.import_customs import find_table, lost_years, normalize, parse_title, summarize

CONFIG = {"top_countries": 2, "top_customs": 2, "top_codes": 2,
          "commodities": [{"hs": "1801", "name_fa": "کاکائو"}, {"hs": "15121", "name_fa": "روغن آفتابگردان"}]}


def row(year, code, tons, usd, month=None, country="ترکیه", customs="تهران", desc="شرح"):
    return {"year": year, "month": month, "customs": customs, "country": country, "code": code, "desc": desc, "tons": tons, "usd": usd}


class TestImportCustoms(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("امارات متحده عربي"), "امارات متحده عربی")
        self.assertEqual(normalize("سایر_x000D_\n"), "سایر")

    def test_parse_title(self):
        self.assertEqual(parse_title("آمار واردات طی ده ماهه سال 1404"), 10)
        self.assertEqual(parse_title("آمار واردات طی سال 1403"), 12)

    def test_find_table_handles_both_column_namings(self):
        rows = [{0: "آمار واردات طی سال 1403"}, {0: "سال", 1: "گمرک", 2: "کشور", 3: "کدتعرفه", 4: "شرح تعرفه",
                                                5: "وزن (کیلوگرم)", 6: "ارزش (ریال)", 7: " ارزش (دلار)"}]
        i, col = find_table(rows)
        self.assertEqual((i, col["usd"], col["kg"], col["month"]), (1, 7, 5, None))
        self.assertIsNone(find_table([{0: "فراداده"}, {0: "عنوان", 1: "فرمول"}]))

    def test_summarize_filters_by_code_prefix_and_keeps_monthly(self):
        files = [(12, [row(1401, "18010090", 10, 50, month=1), row(1401, "18010090", 5, 20, month=3),
                       row(1401, "84819040", 99, 99, month=1, desc="مشمول ردیف 1801"),   # شیرآلات: حذف می‌شود
                       row(1401, "15122910", 7, 7, month=1)]),                           # پنبه‌دانه، نه آفتابگردان
                 (10, [row(1404, "18010090", 4, 40, country="امارات"), row(1404, "15121110", 8, 16)])]
        data = summarize(CONFIG, files)
        cocoa, sun = data["commodities"]
        self.assertEqual(cocoa["years"][0]["tons"], 15)
        self.assertEqual(cocoa["monthly"]["1401"][:3], [10, 0, 5])
        self.assertNotIn("1404", cocoa["monthly"])
        self.assertTrue(cocoa["years"][1]["partial"])
        self.assertEqual(cocoa["years"][1]["months"], 10)
        self.assertEqual(sun["years"][0]["tons"], 0)
        self.assertEqual(sun["years"][1]["tons"], 8)

    def test_same_year_in_two_files_is_an_error(self):
        with self.assertRaises(ValueError):
            summarize(CONFIG, [(12, [row(1403, "18010090", 1, 1)]), (12, [row(1403, "18010090", 2, 2)])])

    def test_lost_years(self):
        new = summarize(CONFIG, [(12, [row(1403, "18010090", 1, 1)])])
        old = {"commodities": [{"hs": "1801", "name_fa": "کاکائو", "years": [{"year": 1402}, {"year": 1403}]}]}
        self.assertEqual(lost_years(new, old), ["کاکائو 1402"])
        self.assertEqual(lost_years(new, {"commodities": [{"hs": "1801", "name_fa": "کاکائو", "rows": []}]}), [])


if __name__ == "__main__":
    unittest.main()

import io
import unittest
import zipfile

from scripts.fetch_prices import SOURCE_FRED, SOURCE_WB, build_dataset
from scripts.fred_source import SourceError
from scripts.worldbank_source import find_file_url, make_fetcher, parse_prices, read_sheet


def make_xlsx():
    """یک فایل xlsx خیلی کوچک شبیه Pink Sheet: سه ردیف توضیح، ردیف نام‌ها، ردیف واحدها، دو ماه داده."""
    strings = ["World Bank Commodity Price Data", "Cocoa", "Beef **", "($/kg)", "($/mt)", "Maize",
               "2026M08", "2026M09", "…"]
    ss = "".join(f"<si><t>{s}</t></si>" for s in strings)

    def row(n, cells):
        return f'<row r="{n}">' + "".join(cells) + "</row>"

    def s(ref, i):
        return f'<c r="{ref}" t="s"><v>{i}</v></c>'

    def v(ref, x):
        return f'<c r="{ref}"><v>{x}</v></c>'

    sheet = ("<worksheet><sheetData>"
             + row(1, [s("A1", 0)])
             + row(5, [s("L5", 1), s("AP5", 2), s("AE5", 5)])           # ستون‌های پراکنده، مثل فایل واقعی
             + row(6, [s("L6", 3), s("AP6", 3), s("AE6", 4)])
             + row(7, [s("A7", 6), v("L7", "5.61"), v("AP7", "7.31"), v("AE7", "213.5")])
             + row(8, [s("A8", 7), v("L8", "5.92"), s("AP8", 8), v("AE8", "220")])  # «…» = داده نیست
             + "</sheetData></worksheet>")
    wb = ('<workbook><sheets><sheet name="Description" sheetId="1" r:id="rId1"/>'
          '<sheet name="Monthly Prices" sheetId="2" r:id="rId2"/></sheets></workbook>')
    rels = ('<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/sharedStrings.xml", f"<sst>{ss}</sst>")
        z.writestr("xl/worksheets/sheet1.xml", "<worksheet><sheetData/></worksheet>")
        z.writestr("xl/worksheets/sheet2.xml", sheet)
    return buf.getvalue()


PAGE = '<a href="https://thedocs.worldbank.org/en/doc/abc-0050012026/related/CMO-Historical-Data-Monthly.xlsx">x</a>'


def fake_get(url):
    return PAGE.encode() if "commodity-markets" in url else make_xlsx()


class TestWorldBankSource(unittest.TestCase):
    def test_reads_right_columns_and_skips_missing(self):
        prices = parse_prices(read_sheet(make_xlsx()))
        self.assertEqual(prices["cocoa"], ("($/kg)", [("2026-08-01", 5.61), ("2026-09-01", 5.92)]))
        self.assertEqual(prices["beef"][1], [("2026-08-01", 7.31)])   # «**» پاک شد؛ «…» رد شد
        self.assertEqual(prices["maize"][0], "($/mt)")

    def test_find_file_url(self):
        self.assertTrue(find_file_url(PAGE).endswith("CMO-Historical-Data-Monthly.xlsx"))
        with self.assertRaises(SourceError):
            find_file_url("<html>no link</html>")

    def test_fetcher_units_start_and_unknown_column(self):
        fetch = make_fetcher(get=fake_get)
        cocoa = fetch("Cocoa", "2026-09-01")
        self.assertEqual(cocoa, {"unit": "U.S. Dollars per Kilogram", "observations": [("2026-09-01", 5.92)]})
        self.assertEqual(fetch("Maize", "2020-01-01")["unit"], "U.S. Dollars per Metric Ton")
        with self.assertRaises(SourceError):
            fetch("Olive oil", "2020-01-01")

    def test_build_routes_each_commodity_to_its_source(self):
        cfg = [
            {"fred_id": "PCOCOUSDM", "name_fa": "کاکائو", "name_en": "Cocoa", "color": "#111111",
             "worldbank": {"column": "Cocoa"}},
            {"fred_id": "PTEAUSDM", "name_fa": "چای", "name_en": "Tea", "color": "#222222"},
        ]
        fred = lambda sid, start: {"unit": "U.S. Cents per Kilogram", "observations": [("2026-07-01", 273.0)]}
        ds, errors = build_dataset(cfg, fred, fetch_worldbank=make_fetcher(get=fake_get))
        self.assertEqual(errors, [])
        cocoa, tea = ds["commodities"]
        self.assertEqual(cocoa["source"], SOURCE_WB)
        self.assertEqual(cocoa["series"][-1]["usd_per_ton"], 5920.0)   # 5.92 دلار بر کیلو = 5920 دلار بر تن
        self.assertEqual(tea["source"], SOURCE_FRED)
        self.assertEqual(tea["series"][-1]["usd_per_ton"], 2730.0)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3

import importlib.util
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "fetch_price_tencent.py"
SPEC = importlib.util.spec_from_file_location("fetch_price_tencent_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

ROUTER_SCRIPT = SCRIPT.with_name("fetch_price_router.py")
ROUTER_SPEC = importlib.util.spec_from_file_location("fetch_price_router_test", ROUTER_SCRIPT)
ROUTER = importlib.util.module_from_spec(ROUTER_SPEC)
assert ROUTER_SPEC.loader is not None
ROUTER_SPEC.loader.exec_module(ROUTER)


def quote_line(code, name, ticker, price, pct):
    fields = ["1", name, ticker, str(price), str(price), str(price)]
    fields.extend([""] * (32 - len(fields)))
    fields.append(str(pct))
    return f'v_{code}="{"~".join(fields)}";'


class FakeResponse:
    def __init__(self, text):
        self.body = text.encode("gb18030")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class SymbolTests(unittest.TestCase):
    def test_market_codes(self):
        self.assertEqual(MODULE.tencent_code("600519.SS"), "sh600519")
        self.assertEqual(MODULE.tencent_code("000001.SZ"), "sz000001")
        self.assertEqual(MODULE.tencent_code("0700.HK"), "hk00700")
        self.assertEqual(MODULE.tencent_code("AAPL"), "usAAPL")
        self.assertIsNone(MODULE.tencent_code("BTC"))

    def test_parse_quote_contract(self):
        text = "\n".join([
            quote_line("sh600519", "贵州茅台", "600519", 1304, -0.05),
            quote_line("usAAPL", "苹果", "AAPL.OQ", 310.21, -0.04),
            quote_line("hk00700", "腾讯控股", "00700", 442, 0.45),
        ])
        parsed = MODULE.parse_quote_text(text, {
            "sh600519": "600519.SS", "usAAPL": "AAPL", "hk00700": "0700.HK",
        })
        self.assertEqual(parsed["600519.SS"]["price"], 1304)
        self.assertEqual(parsed["AAPL"]["pct_chg"], -0.04)
        self.assertEqual(parsed["0700.HK"]["last_close"], 442)
        self.assertEqual(parsed["AAPL"]["bars"], [])

    def test_fetch_many_keeps_failures_explicit(self):
        text = quote_line("usAAPL", "苹果", "AAPL.OQ", 310.21, 0.04)
        with mock.patch.object(MODULE.urllib.request, "urlopen", return_value=FakeResponse(text)):
            rows = MODULE.fetch_many(["AAPL", "BTC"], retries=1)
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(rows[0]["symbol"], "AAPL")
        self.assertFalse(rows[1]["ok"])
        self.assertEqual(rows[1]["error"], "unsupported_symbol")

    def test_network_failure_is_non_fatal(self):
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")):
            rows = MODULE.fetch_many(["AAPL"], retries=1)
        self.assertFalse(rows[0]["ok"])
        self.assertIn("offline", rows[0]["error"])


class RouterTests(unittest.TestCase):
    def test_default_market_classification(self):
        self.assertEqual(ROUTER.classify("600519.SS"), "tushare")
        self.assertEqual(ROUTER.classify("0700.HK"), "tencent")
        self.assertEqual(ROUTER.classify("AAPL"), "finnhub")
        self.assertTrue(ROUTER.is_crypto("BTC"))

    def test_tencent_failures_continue_to_fallback(self):
        payload = {
            "data": [
                {"symbol": "AAPL", "ok": True, "price": 310},
                {"symbol": "0700.HK", "ok": False, "error": "empty_quote"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quotes.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(ROUTER.failed_symbols(path, ["AAPL", "0700.HK"]), ["0700.HK"])


if __name__ == "__main__":
    unittest.main()

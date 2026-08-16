#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_ths_hot_reason as ths  # noqa: E402


class DecodeTests(unittest.TestCase):
    def test_decode_gb18030_payload(self) -> None:
        payload = {
            "errocode": 0,
            "data": [{"code": "000936", "name": "华西股份", "reason": "光芯片+磷化铟"}],
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("gb18030")
        self.assertEqual(ths._decode_json(raw), payload)

    def test_split_reason_tags_deduplicates_and_preserves_order(self) -> None:
        self.assertEqual(
            ths.split_reason_tags("算力租赁+AI政务、算力租赁/数据中心"),
            ["算力租赁", "AI政务", "数据中心"],
        )


class DocumentTests(unittest.TestCase):
    def test_build_document_normalizes_rows_and_quality(self) -> None:
        payload = {
            "errocode": 0,
            "data": [
                {
                    "code": "000936",
                    "name": "华西股份",
                    "reason": "光芯片+磷化铟",
                    "date": "2026-08-14",
                    "close": 6.97,
                    "zhangdie": 0.63,
                    "zhangfu": 9.937,
                    "huanshou": 15.45,
                    "chengjiaoe": 95116,
                    "chengjiaoliang": 1368824,
                    "ddejingliang": 0.58,
                    "market": 33,
                },
                {"code": "bad", "name": "坏记录", "reason": "测试"},
            ],
        }
        document = ths.build_document(payload, "2026-08-14", "https://example.test")

        self.assertEqual(document["status"], "ok")
        self.assertEqual(document["count"], 1)
        self.assertEqual(document["data"][0]["reason_tags"], ["光芯片", "磷化铟"])
        self.assertEqual(document["quality"]["raw_count"], 2)
        self.assertEqual(document["quality"]["reason_count"], 1)
        self.assertEqual(document["quality"]["malformed_row_count"], 1)

    def test_empty_is_valid_result(self) -> None:
        document = ths.build_document({"errocode": 0, "data": []}, "2026-08-15", "https://example.test")
        self.assertEqual(document["status"], "empty")
        self.assertEqual(document["data"], [])

    def test_upstream_error_is_not_silently_treated_as_empty(self) -> None:
        with self.assertRaises(ths.THSHotReasonError):
            ths.build_document(
                {"errocode": 1001, "errormsg": "upstream unavailable", "data": []},
                "2026-08-14",
                "https://example.test",
            )


if __name__ == "__main__":
    unittest.main()

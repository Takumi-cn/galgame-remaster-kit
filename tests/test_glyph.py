import json
import tempfile
import unittest
from pathlib import Path

from vnremaster.glyph import (
    AmbiguousGlyphError,
    GlyphCodec,
    UnmappedGlyphError,
    load_map,
    plan_map,
)


class GlyphCodecTests(unittest.TestCase):
    def setUp(self):
        self.codec = GlyphCodec({"说": "説", "门": "門", "话": "話"})

    def test_encode_and_decode(self):
        self.assertEqual(self.codec.encode("说话"), "説話")
        self.assertEqual(self.codec.decode("説話"), "说话")

    def test_strict_encode_rejects_unmapped_non_ascii(self):
        with self.assertRaises(UnmappedGlyphError):
            self.codec.encode("说中文", strict=True)
        self.assertEqual(self.codec.encode("说中文", strict=False), "説中文")

    def test_ascii_passes_strict_mode(self):
        self.assertEqual(self.codec.encode("OK", strict=True), "OK")

    def test_identity_mapping_is_recognised(self):
        codec = GlyphCodec({"中": "中"})
        report = codec.audit("中A", {ord("中"), ord("A")})
        self.assertTrue(report.ok)
        self.assertFalse(report.unmapped)
        self.assertTrue(report.entries[0].mapped)

    def test_font_missing_is_reported(self):
        codec = GlyphCodec({"说": "説"})
        report = codec.audit("说话", {ord("説")})
        self.assertFalse(report.ok)
        self.assertEqual(report.font_missing, ["话"])
        self.assertEqual(report.unmapped, ["话"])

    def test_ambiguous_target(self):
        codec = GlyphCodec({"说": "説", "說": "説"})
        self.assertEqual(codec.ambiguous_targets, {"説": ["說", "说"]})
        with self.assertRaises(AmbiguousGlyphError):
            codec.decode("説", strict=True)

    def test_map_validation(self):
        with self.assertRaises(ValueError):
            GlyphCodec({"ab": "c"})
        with self.assertRaises(ValueError):
            GlyphCodec({"a": ""})


class GlyphPlanTests(unittest.TestCase):
    def test_identity_and_suggestion(self):
        plan = plan_map(
            "中A说B",
            {ord("中"), ord("説")},
            candidates=GlyphCodec({"说": "説"}),
        )
        self.assertEqual(plan.pairs, {"中": "中", "说": "説"})
        self.assertEqual(plan.covered, ["中"])
        self.assertEqual(plan.suggested, {"说": "説"})
        self.assertEqual(plan.unresolved, [])
        self.assertTrue(plan.as_dict()["pairs"])

    def test_unresolved_when_target_missing(self):
        plan = plan_map(
            "说",
            {ord("中")},
            candidates=GlyphCodec({"说": "説"}),
        )
        self.assertEqual(plan.pairs, {})
        self.assertEqual(plan.unresolved, ["说"])

    def test_no_candidates(self):
        plan = plan_map("中", {ord("中")})
        self.assertEqual(plan.pairs, {"中": "中"})
        self.assertEqual(plan.suggested, {})


class MapLoadingTests(unittest.TestCase):
    def test_load_pairs_format(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "demo",
                        "pairs": {"说": "説", "门": "門"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            codec = load_map(path)
            self.assertEqual(codec.name, "demo")
            self.assertEqual(codec.encode("说门"), "説門")

    def test_load_flat_format(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map.json"
            path.write_text(
                json.dumps({"说": "説"}, ensure_ascii=False), encoding="utf-8"
            )
            codec = load_map(path)
            self.assertEqual(codec.pairs, {"说": "説"})

    def test_example_map_is_valid(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "demo_map.json"
        codec = load_map(path)
        self.assertGreater(len(codec.pairs), 20)
        self.assertEqual(codec.ambiguous_targets, {})


if __name__ == "__main__":
    unittest.main()

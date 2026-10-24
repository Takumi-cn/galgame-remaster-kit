import struct
import tempfile
import unittest
from pathlib import Path

from vnremaster.fontcmap import (
    FontFormatError,
    format_ranges,
    load_cmap,
    missing_chars,
)


def sfnt_with_cmap(subtable: bytes, platform: int = 3, encoding: int = 1) -> bytes:
    cmap = (
        struct.pack(">HH", 0, 1)
        + struct.pack(">HHI", platform, encoding, 12)
        + subtable
    )
    header = struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
    record = b"cmap" + struct.pack(">III", 0, 28, len(cmap))
    return header + record + cmap


def format4(segments: list[tuple[int, int, int]]) -> bytes:
    count = len(segments)
    ends = b"".join(struct.pack(">H", end) for _, end, _ in segments)
    starts = b"".join(struct.pack(">H", start) for start, _, _ in segments)
    deltas = b"".join(struct.pack(">H", delta & 0xFFFF) for _, _, delta in segments)
    range_offsets = b"\x00\x00" * count
    body = (
        struct.pack(">HHHHHHH", 4, 0, 0, count * 2, 0, 0, 0)
        + ends
        + b"\x00\x00"
        + starts
        + deltas
        + range_offsets
    )
    return body[:2] + struct.pack(">H", len(body)) + body[4:]


def format4_with_glyph_array() -> bytes:
    count = 2
    ends = struct.pack(">HH", 0x43, 0xFFFF)
    starts = struct.pack(">HH", 0x41, 0xFFFF)
    deltas = struct.pack(">HH", 0, 1)
    # Segment 0 points at glyphIdArray[0]; segment 0xFFFF uses delta 1.
    range_offsets = struct.pack(">HH", 2 * count, 0)
    glyphs = struct.pack(">HHH", 1, 2, 3)
    body = (
        struct.pack(">HHHHHHH", 4, 0, 0, count * 2, 0, 0, 0)
        + ends
        + b"\x00\x00"
        + starts
        + deltas
        + range_offsets
        + glyphs
    )
    return body[:2] + struct.pack(">H", len(body)) + body[4:]


def format0(mapping: dict[int, int]) -> bytes:
    glyphs = bytearray(256)
    for code, glyph in mapping.items():
        glyphs[code] = glyph
    return struct.pack(">HHH", 0, 262, 0) + bytes(glyphs)


def format6(first: int, glyph_ids: list[int]) -> bytes:
    length = 10 + 2 * len(glyph_ids)
    body = struct.pack(">HHHHH", 6, length, 0, first, len(glyph_ids))
    body += b"".join(struct.pack(">H", glyph) for glyph in glyph_ids)
    return body


def format12(groups: list[tuple[int, int, int]]) -> bytes:
    length = 16 + 12 * len(groups)
    body = struct.pack(">HHIII", 12, 0, length, 0, len(groups))
    for start, end, glyph in groups:
        body += struct.pack(">III", start, end, glyph)
    return body


class SyntheticFontTests(unittest.TestCase):
    def _write_font(self, subtable: bytes, platform: int, encoding: int) -> Path:
        temp = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
        temp.write(sfnt_with_cmap(subtable, platform, encoding))
        temp.close()
        self.addCleanup(Path(temp.name).unlink)
        return Path(temp.name)

    def test_format4_delta_segments(self):
        segments = [
            (0x41, 0x41, 1 - 0x41),
            (0x42, 0x42, 2 - 0x42),
            (0x4E00, 0x4E00, 3 - 0x4E00),
            (0xFFFF, 0xFFFF, 1),
        ]
        font = self._write_font(format4(segments), 3, 1)
        cmap = load_cmap(font)
        self.assertEqual(cmap, frozenset({0x41, 0x42, 0x4E00}))

    def test_format4_glyph_array(self):
        font = self._write_font(format4_with_glyph_array(), 3, 1)
        cmap = load_cmap(font)
        self.assertEqual(cmap, frozenset({0x41, 0x42, 0x43}))

    def test_format0_byte_table(self):
        font = self._write_font(format0({0x41: 1, 0x42: 2}), 1, 0)
        cmap = load_cmap(font)
        self.assertEqual(cmap, frozenset({0x41, 0x42}))

    def test_format6_trimmed_table(self):
        font = self._write_font(format6(0x41, [1, 0, 2]), 3, 1)
        cmap = load_cmap(font)
        self.assertEqual(cmap, frozenset({0x41, 0x43}))

    def test_format12_groups(self):
        font = self._write_font(
            format12([(0x41, 0x43, 1), (0x4E00, 0x4E01, 10)]),
            3,
            10,
        )
        cmap = load_cmap(font)
        self.assertEqual(cmap, frozenset({0x41, 0x42, 0x43, 0x4E00, 0x4E01}))

    def test_missing_cmap(self):
        header = struct.pack(">IHHHH", 0x00010000, 0, 0, 0, 0)
        with tempfile.NamedTemporaryFile(suffix=".ttf", delete=False) as handle:
            handle.write(header)
            name = handle.name
        self.addCleanup(Path(name).unlink)
        with self.assertRaises(FontFormatError):
            load_cmap(name)

    def test_format_ranges(self):
        self.assertEqual(
            format_ranges({0x41, 0x42, 0x43, 0x4E00}),
            [(0x41, 0x43), (0x4E00, 0x4E00)],
        )

    def test_missing_chars(self):
        cmap = {ord("A"), ord("説")}
        self.assertEqual(missing_chars("A说B", cmap), ["说", "B"])


class SystemFontTests(unittest.TestCase):
    def test_ascii_is_covered(self):
        candidates = [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        ]
        font = next((path for path in candidates if path.exists()), None)
        if font is None:
            self.skipTest("no system font available")
        cmap = load_cmap(font)
        self.assertIn(ord("A"), cmap)
        self.assertGreater(len(cmap), 100)


if __name__ == "__main__":
    unittest.main()

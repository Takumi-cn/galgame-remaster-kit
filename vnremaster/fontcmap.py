"""Minimal TrueType/OpenType ``cmap`` reader (no fontTools dependency).

The audit use case is simple: given a font file, which Unicode codepoints
actually have glyphs? That is exactly what the ``cmap`` table answers. This
module supports the common subtable formats found in CJK fonts:

* format 4  - segment mapping to delta values (BMP)
* format 12 - segmented coverage (full Unicode)
* format 6  - trimmed table
* format 0  - byte encoding table

It also accepts TrueType Collections (``ttcf``) and audits the first font in
the collection.
"""

from __future__ import annotations

import struct
from pathlib import Path

__all__ = [
    "FontFormatError",
    "format_ranges",
    "load_cmap",
    "missing_chars",
]

_SFNT_VERSIONS = {b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"}


class FontFormatError(ValueError):
    """The file is not a supported sfnt font."""


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise FontFormatError(f"read past end of font at {offset}")
    return struct.unpack_from(">H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise FontFormatError(f"read past end of font at {offset}")
    return struct.unpack_from(">I", data, offset)[0]


def load_cmap(path: str | Path) -> frozenset[int]:
    """Return the set of Unicode codepoints with a non-zero glyph in *path*."""
    data = Path(path).read_bytes()
    font_offset = 0
    if data[:4] == b"ttcf":
        if len(data) < 16:
            raise FontFormatError("truncated TTC header")
        font_offset = _u32(data, 12)

    if data[font_offset : font_offset + 4] not in _SFNT_VERSIONS:
        raise FontFormatError("not a TrueType/OpenType font")

    num_tables = _u16(data, font_offset + 4)
    tables: dict[bytes, tuple[int, int]] = {}
    for index in range(num_tables):
        record = font_offset + 12 + index * 16
        tag = data[record : record + 4]
        offset = _u32(data, record + 8)
        length = _u32(data, record + 12)
        tables[tag] = (offset, length)

    if b"cmap" not in tables:
        raise FontFormatError("font has no cmap table")
    cmap_offset, cmap_length = tables[b"cmap"]
    return _parse_cmap(data, cmap_offset, cmap_length)


def _parse_cmap(data: bytes, cmap_offset: int, cmap_length: int) -> frozenset[int]:
    version = _u16(data, cmap_offset)
    if version not in (0, 1):
        raise FontFormatError(f"unsupported cmap version {version}")
    count = _u16(data, cmap_offset + 2)
    records: list[tuple[int, int, int]] = []
    for index in range(count):
        record = cmap_offset + 4 + index * 8
        platform = _u16(data, record)
        encoding = _u16(data, record + 2)
        sub_offset = _u32(data, record + 4)
        records.append((platform, encoding, cmap_offset + sub_offset))

    priority = {
        (3, 10): 0,
        (0, 6): 1,
        (0, 4): 2,
        (3, 1): 3,
        (0, 3): 4,
        (0, 0): 5,
    }
    records.sort(key=lambda item: (priority.get((item[0], item[1]), 99), item[2]))
    last_error: Exception | None = None
    for _platform, _encoding, base in records:
        try:
            codepoints = _parse_subtable(data, base)
        except FontFormatError as exc:
            last_error = exc
            continue
        if codepoints:
            return frozenset(codepoints)
    if last_error is not None:
        raise FontFormatError(f"no usable cmap subtable: {last_error}")
    raise FontFormatError("cmap contains no supported subtable")


def _parse_subtable(data: bytes, base: int) -> set[int]:
    fmt = _u16(data, base)
    if fmt == 4:
        return _parse_format4(data, base)
    if fmt == 12:
        return _parse_format12(data, base)
    if fmt == 6:
        return _parse_format6(data, base)
    if fmt == 0:
        return _parse_format0(data, base)
    raise FontFormatError(f"unsupported cmap subtable format {fmt}")


def _parse_format4(data: bytes, base: int) -> set[int]:
    length = _u16(data, base + 2)
    end = min(base + length, len(data))
    if end - base < 16:
        raise FontFormatError("truncated format 4 cmap")
    seg_count = _u16(data, base + 6) // 2
    if seg_count <= 0:
        return set()

    end_codes = base + 14
    start_codes = end_codes + 2 * seg_count + 2
    deltas = start_codes + 2 * seg_count
    range_offsets = deltas + 2 * seg_count
    glyph_array = range_offsets + 2 * seg_count
    if glyph_array > end:
        raise FontFormatError("format 4 arrays exceed subtable length")

    result: set[int] = set()
    for index in range(seg_count):
        start = _u16(data, start_codes + 2 * index)
        stop = _u16(data, end_codes + 2 * index)
        if start > stop:
            continue
        delta = _u16(data, deltas + 2 * index)
        range_offset = _u16(data, range_offsets + 2 * index)
        ro_position = range_offsets + 2 * index

        for code in range(start, stop + 1):
            if code == 0xFFFF:
                continue
            if range_offset == 0:
                glyph = (code + delta) & 0xFFFF
            else:
                glyph_position = ro_position + range_offset + 2 * (code - start)
                if glyph_position + 2 > end:
                    continue
                glyph = _u16(data, glyph_position)
                if glyph:
                    glyph = (glyph + delta) & 0xFFFF
            if glyph:
                result.add(code)
    return result


def _parse_format12(data: bytes, base: int) -> set[int]:
    length = _u32(data, base + 4)
    end = min(base + length, len(data))
    groups = _u32(data, base + 12)
    if base + 16 + groups * 12 > end:
        raise FontFormatError("format 12 groups exceed subtable length")
    result: set[int] = set()
    for index in range(groups):
        record = base + 16 + index * 12
        start = _u32(data, record)
        stop = _u32(data, record + 4)
        start_glyph = _u32(data, record + 8)
        if start > stop or start > 0x10FFFF:
            continue
        stop = min(stop, 0x10FFFF)
        for code in range(start, stop + 1):
            if start_glyph + (code - start):
                result.add(code)
    return result


def _parse_format6(data: bytes, base: int) -> set[int]:
    length = _u16(data, base + 2)
    end = min(base + length, len(data))
    first = _u16(data, base + 6)
    count = _u16(data, base + 8)
    if base + 10 + count * 2 > end:
        raise FontFormatError("format 6 glyph array exceeds subtable length")
    result = set()
    for index in range(count):
        if _u16(data, base + 10 + index * 2):
            result.add(first + index)
    return result


def _parse_format0(data: bytes, base: int) -> set[int]:
    if base + 262 > len(data):
        raise FontFormatError("truncated format 0 cmap")
    return {index for index in range(256) if data[base + 6 + index]}


def format_ranges(codepoints: frozenset[int] | set[int]) -> list[tuple[int, int]]:
    """Group sorted codepoints into inclusive ranges."""
    ordered = sorted(codepoints)
    if not ordered:
        return []
    ranges: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for code in ordered[1:]:
        if code == previous + 1:
            previous = code
            continue
        ranges.append((start, previous))
        start = previous = code
    ranges.append((start, previous))
    return ranges


def missing_chars(text: str, cmap: frozenset[int] | set[int]) -> list[str]:
    """Return characters in *text* whose codepoint is absent from *cmap*."""
    seen: set[str] = set()
    missing: list[str] = []
    for char in text:
        if char in seen or char in "\r\n\t":
            continue
        seen.add(char)
        if ord(char) not in cmap:
            missing.append(char)
    return missing

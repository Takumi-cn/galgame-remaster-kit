# Reading a font's cmap without fontTools

A font's `cmap` table answers one question: for a Unicode codepoint, which glyph
index should be used? For a localization audit that is often enough. This note
documents the subset implemented in `vnremaster/fontcmap.py`.

## 1. sfnt and TTC layout

A TrueType/OpenType file starts with a 12-byte sfnt header:

```text
uint32 sfntVersion   (0x00010000, "OTTO", "true", or "typ1")
uint16 numTables
uint16 searchRange
uint16 entrySelector
uint16 rangeShift
```

It is followed by `numTables` 16-byte records:

```text
char tag[4] | uint32 checksum | uint32 offset | uint32 length
```

A TrueType Collection (`ttcf`) starts with a collection header and an array of
offsets to individual sfnt headers. This tool audits the first face in the
collection. If you need another face, extract it or extend the loader with a
face index.

## 2. cmap header and encoding records

The `cmap` table starts with:

```text
uint16 version
uint16 numTables
```

Each encoding record is 8 bytes:

```text
uint16 platformID
uint16 encodingID
uint32 subtableOffset (relative to the cmap table)
```

Priority used by the reader:

1. `(3, 10)` — Windows, Unicode full repertoire (format 12);
2. `(0, 6)` / `(0, 4)` — Unicode platform, full repertoire;
3. `(3, 1)` — Windows, BMP (format 4);
4. `(0, 3)` — Unicode BMP;
5. `(0, 0)` — Unicode default;
6. any remaining record with a supported format.

If a preferred subtable cannot be parsed, the next record is tried.

## 3. Format 4 (BMP segments)

Format 4 is a set of sorted segments. Each segment has a start code, an end
code, a delta, and a range offset. The arrays are laid out as:

```text
format, length, language, segCountX2, searchRange, entrySelector, rangeShift
endCode[segCount]
reservedPad
startCode[segCount]
idDelta[segCount]
idRangeOffset[segCount]
glyphIdArray[...]
```

For a codepoint `c` in segment `i`:

```text
if idRangeOffset[i] == 0:
    gid = (c + idDelta[i]) & 0xFFFF
else:
    address = &idRangeOffset[i] + idRangeOffset[i] + 2 * (c - startCode[i])
    gid = uint16 at address
    if gid != 0:
        gid = (gid + idDelta[i]) & 0xFFFF
```

A glyph index of 0 means `.notdef`; the codepoint is not covered. The
`0xFFFF` sentinel segment is skipped. The formula is easy to get wrong: the
range offset is relative to the location of the `idRangeOffset` element, not to
the start of the subtable. The synthetic test in `test_fontcmap.py` exercises
both the delta-only and the glyph-array path.

## 4. Format 12 (full Unicode)

Format 12 uses groups:

```text
format, reserved, length, language, nGroups
group[n]: startChar, endChar, startGlyphID
```

For a codepoint `c` in a group, the glyph is
`startGlyphID + (c - startChar)`. A zero result means `.notdef`. Groups can
cover large ranges; the reader clamps to `0x10FFFF` and stores a set of
codepoints.

## 5. Formats 6 and 0

- Format 6 is a trimmed array: `firstCode`, `entryCount`, then a glyph array.
  Codepoint `firstCode + i` is covered when its glyph is non-zero.
- Format 0 is a 256-byte byte-encoding table. It is rare for CJK but cheap to
  support.

## 6. What coverage means

`load_cmap()` returns the set of codepoints with a **non-zero glyph index**.
That is the right check for “will the engine find a glyph?” but not a guarantee
that the glyph looks correct at UI size. A font can contain a codepoint whose
shape is unsuitable for the intended text. Always combine the audit with a
visual check.

The glyph-substitution workflow uses this set as follows:

- identity mapping (`中 -> 中`) when the source codepoint is covered;
- candidate mapping (`说 -> 説`) when the target is covered;
- unresolved when neither the source nor a candidate target is covered.

## 7. Limitations

- Format 2 (high-byte mapping) and format 13 (many-to-one) are not implemented.
- Format 14 (Unicode variation sequences) is not implemented; variation
  selectors are treated as normal codepoints.
- `cmap` maps codepoints to glyph indices, not glyph outlines. This tool does
  not parse `glyf`/CFF, `GSUB`, or shaping tables.
- Only the first face of a TTC is audited.
- Variable fonts are audited using their default instance; the codepoint
  coverage is normally unchanged, but appearance may vary.
- The audit does not model the engine's own fallback font. If the engine has a
  fallback, a “missing” glyph may still render through it; verify in-game.

## 8. Synthetic example

A minimal format 4 subtable in the tests maps:

| codepoint | character | glyph index |
|---:|---:|---:|
| 0x41 | A | 1 |
| 0x42 | B | 2 |
| 0x4E00 | 一 | 3 |
| 0xFFFF | sentinel | 0 |

The test constructs the table by hand, including the `reservedPad` and the
sorted segment arrays, then asserts that the parser returns exactly
`{0x41, 0x42, 0x4E00}`. A second fixture uses a non-zero `idRangeOffset` to
exercise the glyph-array formula.

No font file is committed to this repository; the fixtures are generated in
memory and in temporary files.

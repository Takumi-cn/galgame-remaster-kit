# Methodology

This document describes the generic parts of a legacy visual-novel remastering
workflow. It intentionally omits game titles, file hashes, offsets, and
translated content. The goal is to document the engineering, not to
redistribute or reproduce someone else's work.

## 1. Why legacy visual novels are awkward

A 4:3 visual novel from the 2000s–2010s usually combines four constraints that
do not appear together in modern engines:

1. **Baked UI.** Menus are often pre-rendered images inside a proprietary
   archive, not layout files. Translating a label can mean editing a page
   image and recompressing it.
2. **Engine-drawn text.** Dialogue, character names, tooltips, and some
   settings values are drawn by the engine from compressed text tables, not
   from the page image.
3. **Tight font coverage.** The shipped Japanese font may have no Simplified
   Chinese glyphs. Rebuilding or extending a font is risky: the engine may
   cache glyph widths, atlas pages, or a proprietary font container.
4. **Fixed-size storage.** Assets are often embedded as zlib streams whose
   compressed size is implied by the next stream's offset. A replacement that
   compresses smaller cannot simply be written shorter.

The toolkit in this repository addresses (2)–(4) with generic code and leaves
(1) to an image editor plus the same archive tooling.

## 2. Container archaeology

The PAC container supported here has no index:

```text
"PAC\0" | count | version | zlib stream 0 | zlib stream 1 | ... | footer
```

To find a stream boundary, feed bytes to `zlib.decompressobj()` until it
reports `eof`; the uncompressed length and the number of consumed bytes are
the stream's metadata. The reader scans streams lazily: it records offsets and
sizes, then decompresses a stream only when asked. This keeps memory bounded
for archives with large assets.

The footer after the last stream is preserved as an opaque byte string. The
tool makes no assumption about what it contains.

### Exact-size recompression

A replacement payload usually compresses to a different size. Two cases
matter:

- **Too large.** The payload cannot fit; the asset must be resized,
  re-encoded, or the archive layout must change. This tool refuses rather than
  shifting offsets.
- **Too small.** The stream must be padded to the original compressed size.

Padding cannot be arbitrary trailing bytes: those bytes are not part of the
zlib stream and would be interpreted as the next stream. Instead, append
empty DEFLATE blocks inside the stream:

- an empty stored block costs 5 bytes (3-bit header, byte alignment, 4-byte
  `LEN`/`NLEN`);
- an empty fixed-Huffman block costs 10 bits.

The final appended block sets `BFINAL`. Because the sync-flushed stream is
already byte-aligned, appending blocks is safe. The encoder tries both block
orders and a small range of counts, then verifies the exact length and
`zlib.decompress(out) == payload`.

### Invariants checked by the rebuild path

```text
len(new_archive) == len(old_archive)
stream_count, version unchanged
for every stream: new.csize == old.csize
for untouched streams: compressed bytes identical
footer bytes identical
for replaced streams: decompress(new) == payload
```

The rebuild is parsed again from scratch and the checks are repeated. This is
deliberate paranoia: a subtle offset error can look fine until the game reads
the next asset.

## 3. Localization surfaces

### Baked page images

A settings page may be one or more atlas images. The workflow is:

1. Extract the page image and record its exact compressed size.
2. Remove the old text and match the background (clone a clean region, or
   repaint with the sampled fill).
3. Draw the replacement text with the same font size, weight, stroke, and
   baseline as the original.
4. Save a lossless image and rebuild the stream to the original compressed
   size.
5. Capture the page in-game and compare against the original geometry.

Checklist: slider endpoints, section headers, help text, and any text that is
drawn by the engine rather than baked into the page. A page that looks fine at
the top can hide a wrong row offset at the bottom.

### Equal-length engine strings

Some engines store text in fixed-size slots or require the original character
count. Shortening a string and padding with null bytes can make the
configuration loader reject the file. A safer approach is:

- keep the original character count;
- pad with an ideographic space (`U+3000`) or another accepted filler;
- verify that the engine still loads and displays the string.

This is engine-specific. The important rule is to test the loader, not just
the rendering.

### Glyph substitution instead of font rebuilding

If the font contains a Japanese glyph that is visually close to the desired
Simplified character, replace the character at the text level and keep a
reversible map:

```json
{"说": "説", "门": "門"}
```

Then audit the final text against the font's `cmap`. The audit catches:

- a character with no mapping and no glyph;
- a mapping whose target glyph is absent from the font;
- a target produced by several sources, which makes reverse conversion
  ambiguous.

The tradeoff is visual: the substitute glyph must be acceptable at UI sizes.
The map is a design decision, not an automatic conversion. Do not publish a
game-specific map as if it were a general standard.

### What the tool does not do

- It does not rebuild fonts or modify glyph outlines.
- It does not patch executables or bypass licensing/DRM.
- It does not invent translations or mappings.

## 4. Display pipeline measurement

Legacy games often render at 4:3 and a low internal resolution. A real-time
upscaler can improve perceived sharpness, but the experiment must compare the
right images.

### Compare the final output

A supersampling chain may render at 4K into a virtual framebuffer and let the
driver downsample to a 1440p panel. A screenshot of the 4K framebuffer is
**not** what the panel shows: it has not gone through the final downsample.
Comparing that screenshot to a direct 1440p output overstates the
supersampling result.

A practical approximation used in this project:

1. Capture the direct output at the panel resolution (this is the actual final
   image).
2. Capture the supersampled framebuffer and downsample it with a high-quality
   resampler to the same final content size.
3. Normalize both to identical dimensions and crop the same region.
4. Compare mean absolute difference, PSNR, and edge energy; inspect a 2–4×
   nearest-neighbor crop.

The resampler used for step 2 is not identical to the driver's filter, but it
is a sharper, more generous approximation. If the direct output still wins,
the conclusion is robust.

### Read edge energy with care

Edge energy is a proxy, not a quality score. It increases with real detail,
but also with sharpening halos and aliasing. Always pair it with a visual
check and report the direction of the difference, not just a single number.

### Experiment order that avoided wasted work

For each candidate:

1. Fix the scene and capture timing; confirm repeated captures are
   byte-identical or visually identical.
2. Change one variable (effect chain, capture method, precision, refresh
   mode).
3. Capture the final output; compare normalized crops.
4. Reject over-sharpened results with halos, even if edge energy rises.
5. Keep a baseline config and a one-line rollback path.

In this project, a CAS tail pass, a different upscaler plus a thinning pass,
FP32 precision, and alternate capture methods did not beat the baseline. The
largest gain came from removing an unnecessary resampling stage, not from
adding another sharpener.

### Frame pacing

A 60 FPS game on a 144 Hz panel can show uneven 3:2 cadence. A 120 Hz mode
makes the cadence even, but refresh switching can introduce black screens on
some systems. Treat refresh switching as a separate, reversible decision; do
not bundle it with the upscaler experiment.

## 5. Verification loop

For every localization or archive change:

1. **Static checks.** Parse the rebuilt archive; compare stream count,
   version, sizes, untouched bytes, and footer.
2. **Round-trip checks.** Decompress every replaced stream and compare to the
   payload.
3. **Loader check.** Start the game and confirm the configuration/asset loads
   without an error dialog.
4. **Visual check.** Capture the specific page at the final display setting;
   compare geometry and text against the source.
5. **Rollback check.** Keep the pre-change file and know how to restore it.

The repository's tests mirror steps 1–2 with synthetic archives. They do not
require a game installation and do not read copyrighted data.

## 6. Publishing sanitization

Before publishing a technical write-up:

- remove game titles, company names, file hashes, offsets, and translated
  text;
- replace screenshots with synthetic placeholders or omit them;
- publish tools and methodology, not assets;
- include a clear notice that no game data is bundled;
- run a repository guard that fails on media files, large binaries, absolute
  home paths, and hash-like strings.

See `tools/check_repo.py` for the guard used by this repository.

## Companion notes

- [ui-localization.md](ui-localization.md) — the page-image and engine-text
  workflow in detail.
- [deflate-notes.md](deflate-notes.md) — exact-size streams and the empty-block
  search.
- [cmap-notes.md](cmap-notes.md) — the sfnt/cmap formats implemented by the
  audit.
- [design.md](design.md) — module boundaries, error model, and testing
  strategy.
- [experiment-log.md](experiment-log.md) — the display A/B matrix and decision
  trail.
- [walkthrough.md](walkthrough.md) — a full synthetic CLI session.

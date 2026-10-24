# galgame-remaster-kit

> **中文简介**：一套面向老视觉小说（Galgame）研究的通用工具链：PAC 归档等长重打包、CJK 字形覆盖审计、Windows 窗口采集与画质 A/B 度量。仓库只含代码、文档和合成示例，不含任何游戏资源、汉化文本、截图或补丁。

Small, dependency-light tools for **studying and improving legacy galgames
(Japanese visual novels)** without rebuilding the engine:

- **`pac`** — inspect, verify, diff, summarise, and rebuild sequential-zlib
  PAC archives while keeping every compressed stream exactly the same size.
- **`glyph`** — apply a reversible CJK glyph-substitution table, audit font
  coverage, and generate a starter map from a font plus a text corpus.
- **`compare`** — normalize two images, compute objective A/B metrics, write
  a labeled comparison sheet, and emit an amplified difference map.
- **`windows`** — Windows-only, read-only window enumeration and client-area
  capture for display experiments.

The repository contains **no game assets, translations, screenshots, or
patched builds**. All demo data is generated synthetically. See
[Scope and ethics](#scope-and-ethics).

## Quick start

```bash
python -m pip install -e .
python -m vnremaster demo demo_out

python -m vnremaster pac inspect demo_out/demo.pac
python -m vnremaster pac verify  demo_out/demo.pac
python -m vnremaster pac stats   demo_out/demo.pac
python -m vnremaster pac diff    demo_out/demo.pac demo_out/demo.pac

python -m vnremaster compare \
  demo_out/before.png demo_out/after.png \
  --out demo_out/compare.png --normalize 640x480 --zoom 2 \
  --diff-out demo_out/diff.png

python -m vnremaster glyph plan \
  --font /path/to/japanese-font.ttf --text "说话门" \
  --candidates examples/demo_map.json --out demo_out/plan.json
```

Running from the repository root needs no install: the package is already on
`sys.path`. The editable install is only needed for the `vnremaster` console
script and for running from another directory. It pulls in Pillow; the
archive and cmap code itself is pure standard library.

`demo_out/before.png` and `after.png` are generated placeholder UI images, not
game screenshots. The comparison command prints mean absolute difference,
PSNR, and edge-energy values, then writes a labeled sheet.

## What each tool does

### 1. Exact-size PAC stream replacement

The supported container is deliberately narrow:

```text
offset 0    "PAC\0"
offset 4    uint32 stream count
offset 8    uint32 version
offset 12   stream 0 (complete zlib stream)
            stream 1
            ...
            stream N-1
            trailing bytes (preserved verbatim)
```

There is no index. Each stream ends where zlib reports its final block, so
replacing an asset naively shifts every following offset. The rebuild command
solves the inverse problem: compress the new payload to **exactly** the old
compressed size, then verify the whole archive.

```bash
# Replace stream 3 and write a new file.
python -m vnremaster pac rebuild game.pac \
  --set 3=new_asset.bin --out patched.pac

# Replace in place, keeping a one-time .bak copy.
python -m vnremaster pac rebuild game.pac \
  --set 3=new_asset.bin --in-place
```

How the padding works: after a zlib sync flush the DEFLATE stream is
byte-aligned, so empty stored blocks (5 bytes each) and empty fixed-Huffman
blocks (10 bits each) can be appended without changing the decompressed
payload. The final appended block sets `BFINAL`. The implementation searches
a small space of block counts and orders, then round-trips the result through
`zlib.decompress`.

The rebuild path enforces these invariants:

- total file size unchanged;
- stream count and version unchanged;
- every stream keeps its original compressed size;
- untouched streams are byte-identical;
- trailing bytes are byte-identical;
- every replacement decompresses back to the input payload.

Two read-only commands support experiments and CI:

```bash
# Size histogram, largest streams, and duplicate decompressed payloads.
python -m vnremaster pac stats archive.pac

# Per-stream comparison; --no-content skips payload hashing.
python -m vnremaster pac diff before.pac after.pac
python -m vnremaster pac diff before.pac after.pac --fail-on-diff
```

`diff` distinguishes `same`, `changed`, `only-a`, `only-b`, and
`recompressed` (the stream bytes differ but the decompressed payload is
identical). `--fail-on-diff` returns exit code 1 when anything differs, which
makes it useful as a release check.

### 2. CJK glyph coverage without rebuilding a font

Some Japanese fonts cover the Japanese glyph repertoire but not every
Simplified Chinese character. Rebuilding a font is one answer; a lighter
alternative is to substitute a character with an existing glyph that is
visually equivalent or close, and keep an explicit mapping:

```json
{
  "pairs": {
    "说": "説",
    "门": "門"
  }
}
```

```bash
python -m vnremaster glyph check \
  --map examples/demo_map.json --text "说话" \
  --font /path/to/font.ttf
```

The `font` subcommand is a dependency-free `cmap` reader for TrueType,
OpenType, and TTC files. It supports cmap formats 0, 4, 6, and 12, which
covers the common Japanese and CJK fonts used by legacy games.

The audit reports:

- characters with no mapping entry (`unmapped`);
- encoded characters that the chosen font does not contain
  (`font_missing`);
- ambiguous reverse mappings (one target produced by several sources).

Add identity mappings (`"中": "中"`) for characters that are already present
and do not need substitution.

To build a starter table from a font and a text corpus:

```bash
python -m vnremaster glyph plan \
  --font /path/to/font.ttf --text "说话门" \
  --candidates examples/demo_map.json --out plan.json
```

`plan` writes identity entries for characters the font already covers,
candidate substitutions for characters that can reuse a covered glyph, and an
`unresolved` list for everything else. The output is a normal map file that
`glyph check` and `glyph encode` can consume.

### 3. Display A/B with the right target

The comparison tool is intentionally simple: Pillow only, no NumPy, no GPU
stack. It normalizes both images to the same size, optionally crops a region,
and reports:

- **mean absolute difference** — useful for spotting changed content;
- **PSNR** — useful for compression/resampling damage;
- **edge energy** — a rough acutance proxy (mean response of a 3×3 edge
  filter);
- **changed fraction and maximum difference** — how much of the image changed
  above a configurable threshold;
- **edge ratio** — B/A edge energy, reported only when A has a non-zero
  baseline.

```bash
python -m vnremaster compare \
  before.png after.png --out comparison.png \
  --normalize 1920x1440 --region 200,200,1700,1200 \
  --zoom 2 --stack vertical \
  --diff-out diff.png --threshold 2
```

Methodology matters more than the numbers. Compare the image that **actually
reaches the display**, not an intermediate framebuffer. A 4K supersampling
chain can look very sharp in a 4K framebuffer capture and then lose some of
that sharpness in the final downscale to a 1440p panel. Pair edge metrics
with a visual check: edge energy rewards real detail but also rewards
sharpening halos.

### 4. Window capture (Windows only)

The display experiments need a repeatable capture of exactly the pixels the
game rendered. The `windows` command enumerates top-level windows by PID,
class, title, and client size, then captures the client area with a read-only
GDI BitBlt:

```bash
python -m vnremaster windows list --min-size 800x600 --limit 10
python -m vnremaster windows capture --class DemoWindow --out window.png
python -m vnremaster windows capture --hwnd 0x123456 --out window.png
```

It does not inject, hook, or modify another process, and it refuses to guess a
target when no filter is supplied. The capture reads the screen, so an
occluded window is captured as occluded; use `--bring-to-front` or move it
manually first. On non-Windows platforms the module imports cleanly but the OS
calls raise `WindowError`.

## What this demonstrates

For reviewers, the interesting parts are not the specific game, but the
engineering:

- parsing an undocumented archive without an index;
- working at the DEFLATE bit level to preserve exact stream sizes, including
  the final-block invariant;
- implementing a dependency-free sfnt `cmap` reader for CJK coverage,
  including the format 4 glyph-array path;
- turning font coverage into an actionable map plan rather than a binary
  pass/fail;
- designing an A/B experiment around the actual output, not a convenient
  intermediate;
- a verification loop that proves untouched data did not move, plus diff and
  stats commands for release checks;
- a read-only Windows capture path built on ctypes/GDI;
- a clean-room repository: no copyrighted fixtures, deterministic synthetic
  demos, property-style tests, and CI on Linux and Windows.

## Repository layout

```text
vnremaster/
  deflate.py      exact-size zlib stream construction
  pac.py          PAC reader, verifier, diff/stats, rebuild pipeline
  fontcmap.py     TrueType/OpenType cmap parser
  glyph.py        glyph substitution codec, audit, and map planning
  compare.py      image metrics, comparison sheets, diff heatmaps
  window.py       read-only Windows window enumeration/capture
  demo.py         synthetic PAC and UI fixtures
  __main__.py     command-line interface
  py.typed        PEP 561 typing marker
examples/
  demo_map.json   small illustrative glyph table
  make_demo.py    fixture generator
  pac_workflow.py direct API example: parse, rebuild, diff, stats
  pipeline_demo.py  direct-vs-supersampled resampling demo
tests/            unittest suite (no network, no game data)
docs/             methodology, deep dives, design, experiment log
tools/            repository guard
```

## Tests

```bash
python -m unittest discover -s tests -v
python tools/check_repo.py
python examples/pipeline_demo.py pipeline_out
```

The suite has 70+ deterministic tests. It covers exact-size recompression
(including a final-block check), archive round-trips, untouched-byte
preservation, diff/stats, property-style random archives, synthetic cmap
formats 4 and 12 (including the glyph-array path), glyph audit and map
planning, image metrics, diff heatmaps, comparison-sheet geometry, window
filter logic, and the CLI. CI runs on Ubuntu and Windows with Python
3.10–3.13, then builds and installs the wheel.

## Documentation

- [Methodology](docs/methodology.md) — the full workflow and its constraints.
- [UI localization](docs/ui-localization.md) — baked-page editing, equal-length
  strings, font coverage, and the verification checklist.
- [Sanitized case study](docs/case-study.md) — what was changed and what was
  deliberately not published.
- [DEFLATE notes](docs/deflate-notes.md) — exact-size streams at the bit level.
- [cmap notes](docs/cmap-notes.md) — TrueType/OpenType coverage without
  fontTools.
- [Design notes](docs/design.md) — module graph, invariants, error model, and
  performance.
- [Experiment log](docs/experiment-log.md) — the display A/B matrix and the
  decision trail.
- [Walkthrough](docs/walkthrough.md) — a complete synthetic CLI session.
- [CLI reference](docs/cli-reference.md) — every command and option.
- [FAQ](docs/faq.md) — common questions and deliberate non-goals.
- [References](docs/references.md) — RFCs, specs, and API docs.
- [Security policy](SECURITY.md) — supported versions and threat model.
- [Contributing](CONTRIBUTING.md) — clean-room rules and test expectations.

## Scope and ethics

This is a toolkit for **interoperability, preservation research, and
education**. It does not include or decrypt game data, and it does not
circumvent DRM.

- You must own the game you experiment with.
- Do not redistribute game files, extracted assets, translations, or patched
  builds.
- Do not use this project to publish copyrighted content.
- The authors are not affiliated with any game developer or publisher.

If you publish your own experiments, publish **methodology and tooling**, not
the copyrighted material.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).

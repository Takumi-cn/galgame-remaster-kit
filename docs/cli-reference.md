# CLI reference

Run `python -m vnremaster <command> --help` for the argparse version. This page
summarises the commands and their intended use.

All commands accept `--json` where noted; JSON is intended for scripts, the
human output is a table or a short summary.

## Exit codes

| code | meaning |
|---:|---|
| 0 | completed |
| 1 | a difference/audit finding (e.g. `pac diff --fail-on-diff`, a strict glyph audit, a font with missing characters) |
| 2 | invalid input, missing file, unsupported format, or OS error |

## `pac`

### `pac inspect FILE [--json] [--limit N]`

Scans stream boundaries without keeping the decompressed payloads. Prints
index, offset, compressed size, uncompressed size, and ratio. `--limit 0`
means all.

### `pac verify FILE [--json]`

Decompresses every stream and checks the recorded uncompressed size. This is
the fastest full-integrity check.

### `pac diff A B [--no-content] [--fail-on-diff] [--json]`

Compares two archives stream by stream. Statuses:

- `same` — compressed bytes identical;
- `recompressed` — compressed bytes differ but the decompressed payload hash is
  identical;
- `changed` — payload differs;
- `only-a` / `only-b` — stream exists in one archive only.

`--no-content` skips payload hashing (layout-only comparison).
`--fail-on-diff` returns exit code 1 when anything differs.

### `pac stats FILE [--top N] [--json]`

Decompresses all streams and reports total compressed/uncompressed sizes, a
size histogram, the largest streams, and duplicate payloads by SHA-256.

### `pac rebuild FILE --set INDEX=FILE [...] --out OUT`

Rebuilds selected streams to their original compressed size. Use
`--in-place` instead of `--out` to replace the source atomically; a one-time
`.bak` is created next to it. `--backup-suffix` changes or disables the suffix.

The command refuses a replacement that cannot fit and re-parses the result
before writing.

### `pac demo OUT`

Writes a synthetic archive (and image fixtures) to `OUT`; useful for a quick
smoke test.

## `glyph`

### `glyph check --map FILE --text TEXT [--font FONT] [--strict] [--json]`

With `--font`, audits the mapped text against the font's `cmap` and reports
unmapped characters, missing glyphs, and ambiguous reverse mappings. Without a
font, it applies the map and reports characters that have no mapping entry.

`--strict` makes missing mappings/glyphs raise (exit code 2) instead of being
reported.

### `glyph font --font FONT [--text TEXT] [--json]`

Prints the number of covered codepoints and ranges. With `--text`, reports
characters absent from the font; exit code 1 when any are missing.

### `glyph plan --font FONT (--text TEXT | --text-file FILE) [--candidates MAP] [--out FILE] [--strict] [--json]`

Builds a starter map:

- identity entry for a non-ASCII character already in the font;
- candidate mapping when a table entry's target is in the font;
- `unresolved` otherwise.

The `--out` file is a normal map JSON that `check`/`encode` can consume.

### `glyph encode --map FILE --text TEXT`

Prints the substituted text. Useful for a quick visual check.

## `compare`

```text
compare A B --out PATH [--normalize WxH] [--region X0,Y0,X1,Y1]
            [--zoom N] [--stack vertical|horizontal]
            [--threshold N] [--diff-out PATH] [--diff-amplify N]
            [--label-a TEXT] [--label-b TEXT] [--json]
```

Loads two images, optionally normalizes both to `WxH`, optionally crops the
same region, computes metrics, and writes a labeled sheet. `--diff-out` writes
an amplified max-channel difference map.

Metrics: mean absolute difference, PSNR, edge energy for A and B, edge ratio,
changed fraction above the threshold, max channel difference, and MSE.

## `windows` (Windows only)

### `windows list [--json] [--all] [--min-size WxH] [--class NAME] [--title TEXT] [--pid N] [--limit N]`

Lists top-level windows by client size. Hidden windows require `--all`.

### `windows capture [--hwnd HANDLE | --pid N | --class NAME | --title TEXT] [--min-size WxH] --out PATH [--bring-to-front] [--json]`

Captures the client area of the matching window with a read-only GDI BitBlt.
It refuses to guess when no target/filter is supplied. An occluded window is
captured as occluded; use `--bring-to-front` or move it manually.

## `demo`

```bash
python -m vnremaster demo OUT
```

Writes `demo.pac`, `before.png`, and `after.png` (synthetic). Equivalent to
`pac demo` plus images.

## Examples

See [walkthrough.md](walkthrough.md) for a complete session with real output
from the synthetic fixtures.

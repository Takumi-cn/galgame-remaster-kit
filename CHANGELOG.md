# Changelog

## 0.1.0 — 2026-10-24

Initial public toolkit.

- Sequential-zlib PAC reader with lazy boundary scanning and footer
  preservation.
- Exact-size zlib recompression (empty DEFLATE block padding, final-block
  verification).
- Archive `inspect`, `verify`, `diff`, `stats`, and `rebuild` commands.
- Dependency-free TrueType/OpenType/TTC `cmap` reader (formats 0, 4, 6, 12).
- Reversible CJK glyph-substitution codec, font-coverage audit, and starter
  map planning.
- Image A/B metrics: mean absolute difference, PSNR, edge energy/ratio,
  changed fraction, max channel difference, labeled sheets, and diff
  heatmaps.
- Read-only Windows window enumeration and client-area capture.
- Deterministic synthetic demo fixtures and a resampling pipeline example.
- 70+ unit/property/CLI tests; GitHub Actions matrix on Ubuntu and Windows.
- Repository guard against media files, large binaries, absolute home paths,
  and hash-like strings.

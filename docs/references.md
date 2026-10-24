# References

These are the specifications and API documents that informed the
implementation. They are references, not runtime dependencies.

## Compression

- RFC 1950 — ZLIB Compressed Data Format Specification.
  <https://www.rfc-editor.org/rfc/rfc1950>
- RFC 1951 — DEFLATE Compressed Data Format Specification.
  <https://www.rfc-editor.org/rfc/rfc1951>
- Python `zlib` documentation (compressobj, flush modes, decompressobj):
  <https://docs.python.org/3/library/zlib.html>

## Fonts

- OpenType specification, `cmap` table:
  <https://learn.microsoft.com/en-us/typography/opentype/spec/cmap>
- Apple TrueType Reference Manual, `cmap`:
  <https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6cmap.html>
- Unicode Standard, code point and variation-sequence concepts:
  <https://www.unicode.org/standard/standard.html>

## Images

- Pillow documentation (Image, ImageChops, ImageFilter, ImageStat):
  <https://pillow.readthedocs.io/>
- PSNR definition (signal-to-noise ratio):
  <https://en.wikipedia.org/wiki/Peak_signal-to-noise_ratio>

## Windows capture

- `EnumWindows`:
  <https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumwindows>
- `GetClientRect`:
  <https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getclientrect>
- `BitBlt`:
  <https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-bitblt>
- `GetDIBits`:
  <https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-getdibits>

## Testing

- Python `unittest`:
  <https://docs.python.org/3/library/unittest.html>
- GitHub Actions documentation:
  <https://docs.github.com/actions>

The links above are provided for orientation; the code deliberately does not
fetch anything at runtime or during tests.

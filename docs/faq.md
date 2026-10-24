# FAQ

## Does this repository contain game files or translations?

No. It contains code, documentation, and synthetic fixtures only. There are no
game archives, images, fonts, audio, executables, translated strings, offsets,
or hashes. See [NOTICE.md](../NOTICE.md).

## Why must the compressed size stay the same?

The supported container has no index. Each stream's compressed size is
discovered from where its zlib stream ends, and the next stream starts
immediately after it. A shorter replacement would shift every later offset. The
`deflate` module pads from inside the DEFLATE stream so the compressed size is
preserved. See [deflate-notes.md](deflate-notes.md).

## Why not rebuild the font?

Rebuilding or extending a font is risky in a closed engine: glyph widths,
atlas pages, caching, and a proprietary font container can all be involved. A
reversible substitution table plus a `cmap` audit is cheaper and easier to
verify. The tradeoff is that the substitute glyph must be visually acceptable;
always check it at UI size.

## Why not translate automatically?

Machine translation and automatic glyph selection can produce plausible but
wrong UI text, and the mapping table is a product decision. The toolkit makes
the mapping explicit, auditable, and reversible. It does not ship a translation
database.

## Why compare the final output instead of a 4K framebuffer?

A framebuffer capture has not gone through the final downsample to the panel.
It can look sharper than what the user actually sees. The comparison tool
normalizes both images to the same final content size and can simulate the
downsample with a high-quality resampler. See
[methodology.md](methodology.md).

## Does edge energy mean “higher is better”?

No. It is a proxy for acutance and also rises with sharpening halos and
aliasing. Use it with a visual check and report the direction of the
difference. A candidate with visible halos is rejected even if its edge number
is higher.

## Is there an “extract all assets” command?

No. That is a deliberate boundary. The project supports inspection,
verification, diffing, and rebuilding; it does not ship a one-command dumper.
Users who need individual assets can write a small script against the document
API.

## Does it work on encrypted or compressed containers?

No. It handles a specific sequential-zlib PAC layout. It does not decrypt,
unpack nested containers, or bypass DRM. Other layouts need a separate reader
with the same metadata/verification pattern.

## Is Windows required?

Only for `vnremaster.window` and the `windows` command. The archive, glyph,
font, compare, and demo modules are cross-platform. Windows-specific code
imports cleanly elsewhere and raises `WindowError` when called.

## Does the capture work for HDR or hardware overlays?

BitBlt reads the Windows desktop composition. HDR, exclusive fullscreen,
hardware overlays, and protected content may not be captured correctly. For a
display experiment, use a windowed/borderless mode and verify the capture
against a known test pattern.

## What about decompression bombs?

The parser trusts the zlib stream to terminate. A malicious archive can
decompress to a very large payload and exhaust memory. Treat untrusted archives
as untrusted input; run analysis in a container or with a memory limit. The
repository is a toolkit, not a sandbox.

## Can I use this commercially?

The code is MIT-licensed. The games and assets you use it with have their own
licenses. Owning the tool does not give you rights to redistribute someone
else's content.

## How should I cite it?

Link to the repository and mention the version. The methodology and the
synthetic demo are the reproducible parts; game-specific data is not included.

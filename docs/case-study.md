# Case study: a legacy 4:3 visual novel UI

This is a sanitized account of the workflow that motivated the toolkit. It
contains no game titles, extracted text, hashes, screenshots, or patched
files. The point is to show the engineering decisions and the verification
discipline, not to distribute anyone's assets.

## Scope

The target was a 4:3 Japanese visual novel with:

- pre-rendered settings pages stored as image streams;
- engine-drawn dialogue, character names, tooltips, and some values;
- a Japanese font with incomplete Simplified Chinese coverage;
- a sequential-zlib asset archive with a proprietary footer;
- a 1440p display and a real-time upscaler.

The work split into three tracks:

1. UI image localization (menus, settings pages, confirmations).
2. Engine text localization (help strings, sample messages, values).
3. Display-quality experiments (upscaler chain and output path).

Two titles sharing the same engine family were exercised; the tooling was
kept generic so the same checks apply to both.

## Track 1 — page images

The settings pages were vertically stacked in one scroll container, with tabs
that jump to sections. That layout produced a subtle failure mode: a text row
that looked correct at the top of a page could be offset by one line further
down, leaving the original label visible above or below the replacement.

The process that worked:

1. Capture every page at the native window size, including the scrolled
   bottom and the section boundaries.
2. Record the page image's compressed size and treat it as a hard budget.
3. Clone clean background patches for each text region instead of painting a
   flat rectangle; this preserves paper texture and gradients.
4. Match the original font size, weight, stroke, and baseline.
5. Rebuild the stream to the exact compressed size and verify untouched
   streams byte-for-byte.
6. Re-capture in-game and compare against the source geometry.

The most valuable check was not the visual diff at the top of the page; it was
scrolling to the bottom and confirming that no old row survived under the new
one.

## Track 2 — engine text and glyph coverage

Two kinds of engine text caused most of the friction:

- **Fixed-size slots.** Shortening a string and padding with nulls made the
  configuration loader reject the file. Keeping the original character count
  and padding with an ideographic space fixed it.
- **Sample/preview text.** A label that looked static was actually the first
  few characters of a typewriter-style preview message. The fix belonged in
  the text table, not in the page image.

Instead of rebuilding the font, the text was encoded through a reversible
glyph-substitution table and audited against the font's `cmap`. The audit
separated three cases:

- a character with no mapping and no glyph;
- a target glyph absent from the font;
- an ambiguous reverse mapping.

Proper nouns were intentionally left in their original form. They are shared
by dialogue, voice references, and save data; renaming them globally is a
product decision with compatibility risk, not a mechanical UI fix. The
settings labels themselves were fully localized.

## Track 3 — display quality

The starting pipeline used a 4K virtual desktop, a real-time upscaler to
2880×2160, and driver-level downsampling to a 1440p panel. It looked good, but
the screenshots used to judge it were 4K framebuffer captures, not the final
panel image.

The experiment compared:

- **Path A:** game window → upscaler → 4K framebuffer → driver downsample to
  1440p.
- **Path B:** game window → upscaler → 1440p output at the panel resolution.

Both were normalized to the same final content size. Path B had cleaner glyph
edges and fewer resampling artifacts in 1:1 crops. The likely reason is
simple: Path A adds an upscale and a downsample, and the final downsample
softens text more than the extra source resolution helps. Path B also removed
a display-mode switch and reduced GPU load.

Additional candidates were tested one at a time:

- a contrast-adaptive sharpening tail pass: rejected at high strength due to
  halos; no clear win at low strength;
- a different upscaler plus a thinning pass: cleaner lines, but slightly
  softer text; not a clear win;
- FP32 precision: no visible difference in the test scene; reverted;
- alternate capture methods: one failed to present the scaled window, another
  produced a smaller centered output; the default was kept.

The winner was the simpler path: fewer resampling stages, a verified baseline
upscaler, and no extra sharpening.

## Verification

Every archive change went through:

```text
parse -> rebuild -> re-parse -> compare sizes -> compare untouched bytes
      -> decompress replacements -> launch -> capture -> inspect
```

A separate checksum table tracked the final files and backups. The display
pipeline had its own end-to-end test: launch, wait for the scaling window,
check the destination rectangle, capture, exit, and confirm the desktop mode
was restored.

## What was not published

- No game archives, images, fonts, executables, or translated text.
- No screenshots of the game.
- No game-specific offsets, hashes, or codebook.
- No patched builds.

The public repository contains only the generic tools, synthetic fixtures, and
this methodology. That is deliberate: the reusable value is the engineering,
and the copyrighted material stays with the user's own copy of the game.

## Lessons

1. **Measure the final output.** Intermediate framebuffers lie about
   sharpness.
2. **Exact-size storage changes the problem.** The hard part is not
   compression; it is making the result fit without moving anything else.
3. **A font audit is cheaper than a font rebuild.** A reversible glyph map
   plus a cmap check catches most coverage failures.
4. **Keep a rollback for every experiment.** Display settings and archive
   changes are easy to stack; a one-line revert keeps the search honest.
5. **Publish the method, not the material.** A sanitized technical write-up
   is more durable and more useful to reviewers than a redistributed build.

## Companion docs

- [methodology.md](methodology.md) — the full workflow.
- [deflate-notes.md](deflate-notes.md) — the exact-size stream technique.
- [cmap-notes.md](cmap-notes.md) — the font coverage audit.
- [experiment-log.md](experiment-log.md) — the display experiments behind the
  quality decision.

# UI localization workflow for baked-image engines

This is the image-and-text side of the workflow, generalized and sanitized. It
assumes a legacy engine that draws some UI from page images and some text from
engine tables. It contains no game-specific strings or assets.

## 1. Inventory before editing

Capture every page at the native window size, not at the upscaled size:

- the initial view of each tab;
- the scrolled bottom of each page;
- the section boundaries;
- tooltips and hover help;
- confirmation dialogs;
- any preview/sample box that uses the dialogue renderer.

Record for each page:

- the stream index and its compressed size (the hard budget);
- whether the text is baked into the image or drawn by the engine;
- the font family, size, weight, stroke, and color;
- the exact text box and baseline.

A page that looks correct at the top can hide a wrong row offset lower down.
Scrolling to the bottom is not optional.

## 2. Page-image editing

For each text region:

1. Extract the page image and keep the original.
2. Clone a clean background patch from a nearby area. Avoid a flat fill: paper
   texture, gradients, and scanlines make a flat patch obvious.
3. Match the original font. Compare a rendered sample at 2–4× against the
   original before replacing the whole label.
4. Sample the fill and stroke colors from the original glyphs.
5. Draw with the same anchor and baseline; keep the original line spacing.
6. Remove the old label completely, including anti-aliased edges and any
   shadow/stroke remnants.
7. Save a lossless PNG and rebuild the stream to the original compressed size.

If the new PNG is too large, optimize the PNG (filter/palette/compression)
before reducing dimensions. Never change the page dimensions or the stream
layout to make it fit.

## 3. Engine text

Engine text is usually one of:

- a help/tooltip table;
- a fixed-size string slot;
- a preview/sample message;
- a toast or system dialog string.

Workflow:

1. Find the string in the extracted text and record its slot size and encoding.
2. Decide whether the engine expects a character count, a byte count, or both.
3. If the slot is fixed, keep the original character count and pad with an
   accepted filler (for example an ideographic space). Test the configuration
   loader immediately; a shortened string can make the loader reject the file.
4. If the engine uses a custom glyph codebook, encode the translated text
   through that codebook and verify reverse mapping.
5. Check the preview/sample box separately. It may be the first few characters
   of a typewriter string, not a static label.

The GUI localization and the engine text localization must be verified
together: a page can be fully translated yet still show an old label from a
different layer.

## 4. Font coverage

Build a map with three kinds of entries:

- **identity** — the non-ASCII character already exists in the font;
- **candidate** — a visually equivalent glyph exists (for example a Japanese
  form of the same character);
- **unresolved** — neither exists; the font or the copy must change.

Then:

1. Audit the map against the font's `cmap`.
2. Render the resulting text at the actual UI size and inspect it.
3. Check ambiguous reverse mappings (two sources to one target).
4. Keep proper nouns in their original form unless product requirements say
   otherwise; they are shared by dialogue, voice references, and save data.

The audit proves coverage, not beauty. A covered glyph can still look wrong at
small sizes.

## 5. Layout pitfalls

- **Stacked pages.** Settings pages are often one long scroll container. Tab
  clicks jump to sections; a missed tab can look like a missing translation.
- **Row offset.** A replacement drawn one line too low leaves the original
  text visible above it.
- **Slider endpoints.** Each row has its own endpoint glyphs; two rows can
  produce what looks like a duplicated character.
- **Tab hitboxes.** Tab images and hitboxes can drift; use the visible center
  and verify the selected tab.
- **Ghosting.** Anti-aliased remnants survive a rectangular erase. Clone the
  background, do not just paint over.
- **Scrollbars.** A page capture at the top may not include the bottom row;
  capture the end state too.

## 6. Verification checklist

- [ ] Title/menu labels, including every tab.
- [ ] Each settings page at top, middle, and bottom.
- [ ] Slider endpoints and section headers.
- [ ] Tooltips/help text.
- [ ] Sample/preview message.
- [ ] Confirmation dialogs.
- [ ] No leftover original text at the old position.
- [ ] Archive size, stream count, csize, footer, untouched bytes.
- [ ] Game loads without a configuration error.
- [ ] A rollback copy exists and is documented.

## 7. Publication

Publish the tooling and the methodology, not the translated assets. Keep game
titles, hashes, offsets, screenshots, and translated text out of a public
repository. The sanitized case study in this repository is an example of that
boundary.

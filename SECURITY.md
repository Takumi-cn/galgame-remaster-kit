# Security policy

## Supported versions

This is a research toolkit at version 0.x. Security fixes are applied to the
latest release on the default branch.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability involving:

- memory exhaustion or crashes on malformed archives/fonts/images;
- path traversal or unintended file writes;
- unsafe handling of untrusted input;
- a privacy issue in the window-capture module.

Use the hosting repository's private security advisory feature, or contact the
maintainer through the address listed on the repository profile. Include a
minimal input and reproduction steps. Do not attach copyrighted game data.

## Threat model and known limits

- The PAC parser decompresses zlib streams. A malicious stream can expand to a
  very large payload; the tool does not impose a memory limit. Treat untrusted
  archives as untrusted input and run analysis in a constrained environment if
  necessary.
- The rebuild path writes only to the path you specify. `--in-place` creates a
  one-time backup, but you should still keep your own copy before modifying an
  archive.
- The glyph and font modules parse binary font tables. Bounds checks are
  defensive, but the parsers are not a general-purpose font sandbox.
- The Windows capture module reads the visible desktop with GDI BitBlt. It does
  not inject, hook, or modify another process. It does not bypass protected
  content or DRM.
- No secrets, API keys, or credentials belong in this repository. If you find
  one, report it privately.

## Dependency policy

The only runtime dependency is Pillow. The archive and cmap code uses the
Python standard library. Test and build dependencies are installed only in CI
or a local environment, never at runtime.

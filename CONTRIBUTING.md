# Contributing

Thanks for taking a look. This project is intentionally small and strict about
its clean-room policy.

## Ground rules

- **No game assets.** Do not add game archives, images, fonts, audio,
  executables, translated strings, or extracted data.
- **No game-specific offsets or keys.** Generic format support is welcome;
  a patch for one commercial release is not.
- **No network in tests.** Fixtures must be generated locally and
  deterministically.
- **No extraction dumper.** The project stops at inspection, verification,
  diffing, and rebuilding.

## Before opening a pull request

```bash
python -m unittest discover -s tests -v
python tools/check_repo.py
```

If you add a feature:

1. Add a test that fails without it.
2. Keep the error model: format errors, repack errors, and exact-size errors
   are separate exception types.
3. For archive changes, verify the full set of invariants (size, csize,
   untouched bytes, footer, round-trip).
4. For Windows-only code, keep the module importable on other platforms and
   test the pure logic there.
5. Update the relevant document in `docs/` and the README if the CLI changes.

## Code style

- Python 3.10+.
- Type hints on public functions.
- Standard library first; Pillow is the only runtime dependency.
- Prefer small, explicit functions over a framework.
- Keep comments for non-obvious invariants and format details; do not narrate
  what the code already says.

## Reporting a bug

Include:

- the command and the smallest synthetic input that reproduces it;
- expected vs actual output;
- Python version and OS;
- whether the input is an archive, a font, or an image (do not attach
  copyrighted game data).

## License

By contributing, you agree that your contribution is licensed under the MIT
license in `LICENSE`.

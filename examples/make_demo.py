"""Generate the synthetic fixtures used in the README walkthrough."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vnremaster.demo import make_bundle  # noqa: E402


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "demo_out")
    for kind, path in make_bundle(target).items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()

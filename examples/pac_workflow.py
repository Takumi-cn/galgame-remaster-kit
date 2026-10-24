"""Use the archive API directly: parse, inspect, rebuild, diff.

Run from the repository root:

    python examples/pac_workflow.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vnremaster.demo import make_demo_pac  # noqa: E402
from vnremaster.pac import PacArchive  # noqa: E402


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "demo_out")
    source = make_demo_pac(output / "workflow.pac")

    archive = PacArchive.from_file(source)
    print(
        f"source: {archive.count} streams, version {archive.version}, "
        f"footer {len(archive.tail)} bytes"
    )
    for info in archive.streams:
        print(
            f"  stream {info.index}: csize={info.csize} usize={info.usize} "
            f"ratio={info.ratio:.3f}"
        )

    replacement = b"replacement payload\n"
    rebuilt_bytes = archive.rebuild({0: replacement})
    rebuilt_path = output / "workflow_rebuilt.pac"
    rebuilt_path.write_bytes(rebuilt_bytes)

    rebuilt = PacArchive.from_file(rebuilt_path)
    print(
        f"rebuilt: {len(rebuilt_bytes)} bytes, "
        f"stream 0 -> {rebuilt.read_stream(0)!r}"
    )

    diff = archive.diff(rebuilt)
    print(
        f"diff: different={diff.different}, "
        f"changed={diff.changed_count}, footer_same={diff.tail_equal}"
    )
    for item in diff.streams:
        if item.status != "same":
            print(f"  stream {item.index}: {item.status}")

    stats = archive.stats(top=3)
    print(
        f"stats: csize={stats.total_csize} usize={stats.total_usize} "
        f"ratio={stats.ratio:.3f} duplicates={len(stats.duplicates)}"
    )


if __name__ == "__main__":
    main()

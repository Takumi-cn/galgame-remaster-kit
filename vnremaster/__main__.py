"""Command-line entry points: ``python -m vnremaster``."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import __version__
from .compare import (
    compare_images,
    load_rgb,
    make_comparison,
    make_diff_heatmap,
    normalize_size,
)
from .demo import make_bundle
from .fontcmap import format_ranges, load_cmap, missing_chars
from .glyph import load_map, plan_map
from .pac import PacArchive, PacFormatError, RepackError, write_archive
from .window import WindowError, capture_client, find_window, list_windows


def _size(value: str) -> tuple[int, int]:
    normalised = value.lower().replace("×", "x")
    try:
        width, height = normalised.split("x")
        return int(width), int(height)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("expected WxH, e.g. 1920x1440") from exc


def _region(value: str) -> tuple[int, int, int, int]:
    try:
        parts = [int(part) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected X0,Y0,X1,Y1"
        ) from exc
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("expected X0,Y0,X1,Y1")
    return parts[0], parts[1], parts[2], parts[3]


def _hwnd(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a decimal or 0x-prefixed HWND") from exc


def _assignments(values: list[str]) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected INDEX=FILE, got {value!r}")
        index_text, file_text = value.split("=", 1)
        try:
            index = int(index_text)
        except ValueError as exc:
            raise ValueError(f"invalid stream index: {index_text!r}") from exc
        if index in result:
            raise ValueError(f"stream {index} assigned more than once")
        result[index] = Path(file_text)
    return result


def _json_print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _configure_stdio() -> None:
    """Prefer UTF-8 on terminals that support it; never crash on legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _cmd_pac(args: argparse.Namespace) -> int:
    if args.pac_command == "demo":
        path = make_bundle(args.out)["pac"]
        print(path)
        return 0

    archive_path = args.a if args.pac_command == "diff" else args.file
    archive = PacArchive.from_file(archive_path)
    if args.pac_command == "inspect":
        limit = args.limit if args.limit > 0 else archive.count
        streams = [
            {
                "index": info.index,
                "offset": info.offset,
                "csize": info.csize,
                "usize": info.usize,
                "ratio": round(info.ratio, 4),
            }
            for info in archive.streams[:limit]
        ]
        payload = {
            "file": str(args.file),
            "version": archive.version,
            "count": archive.count,
            "tail_bytes": len(archive.tail),
            "sha256": hashlib.sha256(archive.data).hexdigest(),
            "streams": streams,
        }
        if args.json:
            _json_print(payload)
            return 0
        print(
            f"{args.file}: version={archive.version} streams={archive.count} "
            f"tail={len(archive.tail)} bytes"
        )
        print(f"{'idx':>4} {'offset':>10} {'csize':>10} {'usize':>10} {'ratio':>7}")
        for item in streams:
            print(
                f"{item['index']:>4} {item['offset']:>10} {item['csize']:>10} "
                f"{item['usize']:>10} {item['ratio']:>7.3f}"
            )
        return 0

    if args.pac_command == "verify":
        archive.verify()
        payload = {
            "file": str(args.file),
            "version": archive.version,
            "count": archive.count,
            "tail_bytes": len(archive.tail),
            "sha256": hashlib.sha256(archive.data).hexdigest(),
            "ok": True,
        }
        if args.json:
            _json_print(payload)
        else:
            print(
                f"OK: {archive.count} streams, version {archive.version}, "
                f"footer {len(archive.tail)} bytes, all streams decompress"
            )
        return 0

    if args.pac_command == "diff":
        other = PacArchive.from_file(args.b)
        result = archive.diff(other, compare_content=not args.no_content)
        payload = {
            "a": str(args.a),
            "b": str(args.b),
            "version_a": result.version_a,
            "version_b": result.version_b,
            "count_a": result.count_a,
            "count_b": result.count_b,
            "tail_equal": result.tail_equal,
            "different": result.different,
            "changed_count": result.changed_count,
            "streams": [
                {
                    "index": item.index,
                    "status": item.status,
                    "csize_a": item.csize_a,
                    "csize_b": item.csize_b,
                    "usize_a": item.usize_a,
                    "usize_b": item.usize_b,
                    "digest_a": item.digest_a,
                    "digest_b": item.digest_b,
                }
                for item in result.streams
            ],
        }
        if args.json:
            _json_print(payload)
        else:
            print(
                f"A: version={result.version_a} streams={result.count_a} | "
                f"B: version={result.version_b} streams={result.count_b} | "
                f"footer {'same' if result.tail_equal else 'DIFFERENT'}"
            )
            if not result.different:
                print("archives are identical")
            else:
                print(f"differences: {result.changed_count}")
                print(
                    f"{'idx':>4} {'status':<12} {'A csize/usize':>17} "
                    f"{'B csize/usize':>17}"
                )
                for item in result.streams:
                    if item.status == "same":
                        continue
                    left = (
                        f"{item.csize_a}/{item.usize_a}"
                        if item.csize_a is not None
                        else "-"
                    )
                    right = (
                        f"{item.csize_b}/{item.usize_b}"
                        if item.csize_b is not None
                        else "-"
                    )
                    print(
                        f"{item.index:>4} {item.status:<12} {left:>17} {right:>17}"
                    )
        return 1 if (args.fail_on_diff and result.different) else 0

    if args.pac_command == "stats":
        summary = archive.stats(top=args.top)
        payload = {
            "file": str(args.file),
            "version": summary.version,
            "count": summary.count,
            "total_csize": summary.total_csize,
            "total_usize": summary.total_usize,
            "tail_bytes": summary.tail_bytes,
            "ratio": round(summary.ratio, 4),
            "histogram": dict(summary.histogram),
            "duplicates": [
                {"digest": digest, "indices": list(indices), "usize": usize}
                for digest, indices, usize in summary.duplicates
            ],
            "largest": [
                {
                    "index": info.index,
                    "csize": info.csize,
                    "usize": info.usize,
                }
                for info in summary.largest
            ],
        }
        if args.json:
            _json_print(payload)
        else:
            print(
                f"{args.file}: {summary.count} streams, version {summary.version}, "
                f"{summary.total_csize} -> {summary.total_usize} bytes "
                f"(ratio {summary.ratio:.3f}), footer {summary.tail_bytes} bytes"
            )
            print("size histogram: " + ", ".join(
                f"{label}={count}" for label, count in summary.histogram
            ))
            print("largest streams:")
            for info in summary.largest:
                print(
                    f"  {info.index:>4} csize={info.csize:>8} "
                    f"usize={info.usize:>8}"
                )
            if summary.duplicates:
                print(f"duplicate payloads: {len(summary.duplicates)}")
                for digest, indices, usize in summary.duplicates[:5]:
                    print(
                        f"  {digest[:12]} streams={list(indices)} usize={usize}"
                    )
            else:
                print("duplicate payloads: none")
        return 0

    if args.pac_command == "rebuild":
        if args.in_place and args.out:
            raise ValueError("choose either --out or --in-place")
        if not args.in_place and not args.out:
            raise ValueError("an --out path is required unless --in-place is used")
        assignments = _assignments(args.set)
        payloads = {index: path.read_bytes() for index, path in assignments.items()}
        rebuilt = archive.rebuild(payloads)
        if args.in_place:
            target = write_archive(
                args.file,
                rebuilt,
                in_place=True,
                original=archive.data,
                backup_suffix=args.backup_suffix,
            )
        else:
            target = write_archive(args.out, rebuilt)
        result = {
            "file": str(target),
            "replaced": sorted(payloads),
            "size": len(rebuilt),
            "sha256": hashlib.sha256(rebuilt).hexdigest(),
        }
        if args.json:
            _json_print(result)
        else:
            print(
                f"wrote {target}: {len(rebuilt)} bytes, replaced "
                f"{', '.join(map(str, sorted(payloads)))}"
            )
        return 0

    raise ValueError(f"unknown pac command: {args.pac_command}")


def _cmd_glyph(args: argparse.Namespace) -> int:
    codec = load_map(args.map) if getattr(args, "map", None) else None

    if args.glyph_command == "encode":
        assert codec is not None
        print(codec.encode(args.text))
        return 0

    if args.glyph_command == "font":
        cmap = load_cmap(args.font)
        ranges = format_ranges(cmap)
        payload = {
            "font": str(args.font),
            "codepoints": len(cmap),
            "ranges": len(ranges),
        }
        missing: list[str] = []
        if args.text:
            missing = missing_chars(args.text, cmap)
            payload["missing"] = missing
            payload["ok"] = not missing
        if args.json:
            _json_print(payload)
        else:
            print(
                f"{args.font}: {len(cmap)} codepoints in {len(ranges)} ranges"
            )
            if args.text:
                if missing:
                    print("missing: " + "".join(missing))
                else:
                    print("all characters covered")
        return 1 if missing else 0

    if args.glyph_command == "plan":
        if bool(args.text) == bool(args.text_file):
            raise ValueError("provide exactly one of --text or --text-file")
        if args.text_file:
            text = Path(args.text_file).read_text(encoding="utf-8")
        else:
            text = args.text
        cmap = load_cmap(args.font)
        candidates = load_map(args.candidates) if args.candidates else None
        plan = plan_map(text, cmap, candidates=candidates)
        payload = plan.as_dict()
        payload.update(
            {
                "summary": plan.summary(),
                "ok": not plan.unresolved,
                "covered": plan.covered,
                "suggested": plan.suggested,
            }
        )
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(plan.as_dict(), ensure_ascii=False, indent=2) + chr(10),
                encoding="utf-8",
            )
        if args.json:
            _json_print(payload)
        else:
            print(plan.summary())
            if plan.covered:
                print("covered by font: " + "".join(plan.covered))
            if plan.suggested:
                print(
                    "suggested: "
                    + ", ".join(
                        f"{source}->{target}"
                        for source, target in plan.suggested.items()
                    )
                )
            if plan.unresolved:
                print("unresolved: " + "".join(plan.unresolved))
            if args.out:
                print(f"wrote {out_path}")
        return 1 if (args.strict and plan.unresolved) else 0

    if args.glyph_command == "check":
        assert codec is not None
        if args.font:
            cmap = load_cmap(args.font)
            report = codec.audit(args.text, cmap, strict=args.strict)
            payload = {
                "map": str(args.map),
                "font": str(args.font),
                "summary": report.summary(),
                "ok": report.ok,
                "unmapped": report.unmapped,
                "font_missing": report.font_missing,
                "ambiguous_targets": report.ambiguous_targets,
                "entries": [
                    {
                        "source": entry.source,
                        "encoded": entry.encoded,
                        "mapped": entry.mapped,
                        "in_font": entry.in_font,
                    }
                    for entry in report.entries
                ],
            }
            if args.json:
                _json_print(payload)
            else:
                print(report.summary())
                for entry in report.entries:
                    flag = "OK" if entry.in_font else "MISSING"
                    print(
                        f"  {entry.source} -> {entry.encoded} "
                        f"({'mapped' if entry.mapped else 'passthrough'}, {flag})"
                    )
                if report.font_missing:
                    print("font missing: " + "".join(report.font_missing))
            return 0 if report.ok else 1

        encoded = codec.encode(args.text, strict=args.strict)
        unmapped = sorted(
            {
                char
                for char in args.text
                if ord(char) >= 128 and char not in codec.pairs
            }
        )
        payload = {
            "map": str(args.map),
            "encoded": encoded,
            "unmapped": unmapped,
            "ok": not (args.strict and unmapped),
        }
        if args.json:
            _json_print(payload)
        else:
            print(encoded)
            if unmapped:
                print("unmapped: " + "".join(unmapped))
        return 0 if payload["ok"] else 1

    raise ValueError(f"unknown glyph command: {args.glyph_command}")


def _cmd_windows(args: argparse.Namespace) -> int:
    if args.window_command == "list":
        windows = list_windows(
            visible_only=not args.all,
            min_size=args.min_size,
        )
        windows = [
            window
            for window in windows
            if window.matches(
                pid=args.pid,
                class_name=args.class_name,
                title_contains=args.title,
                min_size=args.min_size,
                visible_only=not args.all,
            )
        ]
        windows.sort(key=lambda window: window.area, reverse=True)
        if args.limit > 0:
            windows = windows[: args.limit]
        if args.json:
            _json_print(
                {
                    "count": len(windows),
                    "windows": [
                        {
                            "hwnd": hex(window.hwnd),
                            "pid": window.pid,
                            "class_name": window.class_name,
                            "title": window.title,
                            "width": window.width,
                            "height": window.height,
                            "visible": window.visible,
                        }
                        for window in windows
                    ],
                }
            )
        else:
            print(f"{'hwnd':>12} {'pid':>7} {'size':>12}  class / title")
            for window in windows:
                print(
                    f"{hex(window.hwnd):>12} {window.pid:>7} "
                    f"{window.width:>5}x{window.height:<5} "
                    f"{window.class_name} / {window.title}"
                )
        return 0

    if args.window_command == "capture":
        if args.hwnd is not None:
            hwnd = args.hwnd
            window = None
        else:
            if not any((args.pid, args.class_name, args.title)):
                raise WindowError(
                    "provide --hwnd or at least one of --pid/--class/--title"
                )
            window = find_window(
                pid=args.pid,
                class_name=args.class_name,
                title_contains=args.title,
                min_size=args.min_size,
            )
            if window is None:
                raise WindowError("no matching window")
            hwnd = window.hwnd
        image = capture_client(hwnd, bring_to_front=args.bring_to_front)
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
        payload = {
            "hwnd": hex(hwnd),
            "width": image.width,
            "height": image.height,
            "out": str(output),
        }
        if window is not None:
            payload["pid"] = window.pid
            payload["class_name"] = window.class_name
            payload["title"] = window.title
        if args.json:
            _json_print(payload)
        else:
            print(
                f"captured {hex(hwnd)} {image.width}x{image.height} -> {output}"
            )
        return 0

    raise ValueError(f"unknown windows command: {args.window_command}")


def _cmd_compare(args: argparse.Namespace) -> int:
    a = load_rgb(args.a)
    b = load_rgb(args.b)
    if args.normalize:
        a = normalize_size(a, args.normalize)
        b = normalize_size(b, args.normalize)
    if a.size != b.size:
        raise ValueError(
            f"image sizes differ ({a.size} vs {b.size}); use --normalize WxH"
        )
    metrics = compare_images(a, b, region=args.region, threshold=args.threshold)
    if args.region:
        a_sheet = a.crop(args.region)
        b_sheet = b.crop(args.region)
    else:
        a_sheet, b_sheet = a, b
    label_a = args.label_a or Path(args.a).name
    label_b = args.label_b or Path(args.b).name
    out = make_comparison(
        a_sheet,
        b_sheet,
        args.out,
        label_a=label_a,
        label_b=label_b,
        zoom=args.zoom,
        stack=args.stack,
    )
    diff_path = None
    if args.diff_out:
        diff_path = make_diff_heatmap(
            a_sheet, b_sheet, args.diff_out, amplify=args.diff_amplify
        )
    if args.json:
        payload = {"comparison": str(out), **metrics.as_dict()}
        if diff_path:
            payload["diff_heatmap"] = str(diff_path)
        _json_print(payload)
    else:
        print(f"comparison: {out}")
        print(
            f"size {metrics.width}x{metrics.height} | "
            f"mean_abs_diff {metrics.mean_abs_diff:.4f} | "
            f"psnr {metrics.psnr_db} dB | "
            f"changed {metrics.changed_fraction:.2%} "
            f"(>{metrics.threshold}) | max {metrics.max_abs_diff}"
        )
        print(
            f"edge_energy {metrics.edge_energy_a:.4f} -> "
            f"{metrics.edge_energy_b:.4f} "
            f"(ratio {metrics.edge_ratio if metrics.edge_ratio is not None else 'n/a'})"
        )
        if diff_path:
            print(f"diff heatmap: {diff_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vnremaster",
        description="Legacy visual-novel archive, glyph, and display A/B toolkit.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    pac = sub.add_parser("pac", help="inspect/verify/rebuild sequential-zlib PAC files")
    pac_sub = pac.add_subparsers(dest="pac_command", required=True)
    inspect = pac_sub.add_parser("inspect", help="list streams without decompressing")
    inspect.add_argument("file")
    inspect.add_argument("--json", action="store_true")
    inspect.add_argument("--limit", type=int, default=0)
    verify = pac_sub.add_parser("verify", help="decompress every stream")
    verify.add_argument("file")
    verify.add_argument("--json", action="store_true")
    diff = pac_sub.add_parser("diff", help="compare two archives stream by stream")
    diff.add_argument("a")
    diff.add_argument("b")
    diff.add_argument("--no-content", action="store_true", help="skip payload hashing")
    diff.add_argument("--fail-on-diff", action="store_true", help="exit 1 when different")
    diff.add_argument("--json", action="store_true")
    stats = pac_sub.add_parser("stats", help="size histogram, largest streams, duplicates")
    stats.add_argument("file")
    stats.add_argument("--top", type=int, default=10)
    stats.add_argument("--json", action="store_true")
    rebuild = pac_sub.add_parser("rebuild", help="replace streams with exact-size recompression")
    rebuild.add_argument("file")
    rebuild.add_argument("--set", action="append", default=[], metavar="INDEX=FILE")
    rebuild.add_argument("--out")
    rebuild.add_argument("--in-place", action="store_true")
    rebuild.add_argument("--backup-suffix", default=".bak")
    rebuild.add_argument("--json", action="store_true")
    demo = pac_sub.add_parser("demo", help="write a synthetic archive")
    demo.add_argument("out")

    glyph = sub.add_parser("glyph", help="CJK glyph substitution and font coverage")
    glyph_sub = glyph.add_subparsers(dest="glyph_command", required=True)
    check = glyph_sub.add_parser("check", help="audit text against a map and font")
    check.add_argument("--map", required=True)
    check.add_argument("--text", required=True)
    check.add_argument("--font")
    check.add_argument("--strict", action="store_true")
    check.add_argument("--json", action="store_true")
    font = glyph_sub.add_parser("font", help="inspect a font's cmap coverage")
    font.add_argument("--font", required=True)
    font.add_argument("--text")
    font.add_argument("--json", action="store_true")
    plan = glyph_sub.add_parser("plan", help="build a starter glyph map from a font")
    plan.add_argument("--font", required=True)
    plan.add_argument("--text")
    plan.add_argument("--text-file")
    plan.add_argument("--candidates")
    plan.add_argument("--out")
    plan.add_argument("--strict", action="store_true")
    plan.add_argument("--json", action="store_true")
    encode = glyph_sub.add_parser("encode", help="apply a glyph map to text")
    encode.add_argument("--map", required=True)
    encode.add_argument("--text", required=True)

    compare = sub.add_parser("compare", help="compare two images and write a labeled sheet")
    compare.add_argument("a")
    compare.add_argument("b")
    compare.add_argument("--out", required=True)
    compare.add_argument("--normalize", type=_size, metavar="WxH")
    compare.add_argument("--region", type=_region, metavar="X0,Y0,X1,Y1")
    compare.add_argument("--zoom", type=int, default=1)
    compare.add_argument("--stack", choices=["vertical", "horizontal"], default="vertical")
    compare.add_argument("--threshold", type=int, default=2, help="changed-pixel threshold")
    compare.add_argument("--diff-out", help="write an amplified difference map")
    compare.add_argument("--diff-amplify", type=int, default=4)
    compare.add_argument("--label-a")
    compare.add_argument("--label-b")
    compare.add_argument("--json", action="store_true")

    windows = sub.add_parser("windows", help="list/capture windows (Windows only)")
    window_sub = windows.add_subparsers(dest="window_command", required=True)
    win_list = window_sub.add_parser("list", help="list visible top-level windows")
    win_list.add_argument("--json", action="store_true")
    win_list.add_argument("--all", action="store_true", help="include hidden windows")
    win_list.add_argument("--min-size", type=_size, default=(1, 1))
    win_list.add_argument("--class", dest="class_name")
    win_list.add_argument("--title")
    win_list.add_argument("--pid", type=int)
    win_list.add_argument("--limit", type=int, default=30)
    win_capture = window_sub.add_parser("capture", help="capture a window's client area")
    win_capture.add_argument("--hwnd", type=_hwnd)
    win_capture.add_argument("--pid", type=int)
    win_capture.add_argument("--class", dest="class_name")
    win_capture.add_argument("--title")
    win_capture.add_argument("--min-size", type=_size, default=(1, 1))
    win_capture.add_argument("--out", required=True)
    win_capture.add_argument("--bring-to-front", action="store_true")
    win_capture.add_argument("--json", action="store_true")

    demo = sub.add_parser("demo", help="write synthetic PAC and image fixtures")
    demo.add_argument("out")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "pac":
            return _cmd_pac(args)
        if args.command == "glyph":
            return _cmd_glyph(args)
        if args.command == "compare":
            return _cmd_compare(args)
        if args.command == "windows":
            return _cmd_windows(args)
        if args.command == "demo":
            paths = make_bundle(args.out)
            for kind, path in paths.items():
                print(f"{kind}: {path}")
            return 0
    except (PacFormatError, RepackError, WindowError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

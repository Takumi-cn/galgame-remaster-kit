"""Synthetic demo assets.

Everything generated here is original placeholder content: a tiny PAC archive
with three zlib streams and a footer, plus two blocky UI images for the A/B
tool. No game data is read or written.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

__all__ = ["make_demo_images", "make_demo_pac", "make_bundle"]


def _pseudo_random(count: int, seed: bytes = b"galgame-remaster-kit") -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < count:
        out += hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
        counter += 1
    return bytes(out[:count])


def make_demo_pac(path: str | Path) -> Path:
    """Create a small sequential-zlib archive with a non-empty footer."""
    streams = [
        b"Synthetic asset stream.\n" * 32,
        _pseudo_random(4096),
        bytes(range(256)) * 8,
    ]
    header = b"PAC\x00" + struct.pack("<II", len(streams), 3)
    tail = b"DEMO-TRAILER\x00\x01"
    payload = header + b"".join(zlib.compress(item, 9) for item in streams) + tail
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _draw_ui(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), (18, 28, 48))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        color = (
            int(18 + 24 * t),
            int(28 + 44 * t),
            int(48 + 70 * t),
        )
        draw.line([(0, y), (width, y)], fill=color)

    margin = max(8, width // 24)
    title_size = max(14, height // 10)
    body_size = max(10, height // 22)
    draw.text(
        (margin, margin),
        "DEMO UI",
        fill=(240, 246, 255),
        font=_font(title_size),
    )
    draw.rectangle(
        [margin, height // 3, width - margin, height - margin],
        outline=(150, 200, 255),
        width=max(1, width // 320),
    )
    labels = ("START", "OPTIONS", "EXIT")
    for index, label in enumerate(labels):
        y = height // 3 + margin + index * (body_size + margin)
        draw.text((margin * 2, y), label, fill=(210, 230, 255), font=_font(body_size))

    # A few thin diagonal lines give edge metrics something to measure.
    for offset in range(-height, width, max(12, width // 40)):
        draw.line(
            [(offset, height), (offset + height, 0)],
            fill=(70, 120, 170),
            width=1,
        )
    return image


def make_demo_images(directory: str | Path) -> tuple[Path, Path]:
    """Create a deliberately soft image and a sharper, full-size counterpart."""
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    after = _draw_ui(640, 480)
    after = after.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=2))
    after_path = target_dir / "after.png"
    after.save(after_path)

    low = _draw_ui(320, 240)
    low = low.resize((640, 480), Image.Resampling.BICUBIC)
    low = low.filter(ImageFilter.GaussianBlur(0.6))
    before_path = target_dir / "before.png"
    low.save(before_path)
    return before_path, after_path


def make_bundle(directory: str | Path) -> dict[str, Path]:
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    pac_path = make_demo_pac(target_dir / "demo.pac")
    before, after = make_demo_images(target_dir)
    return {"pac": pac_path, "before": before, "after": after}

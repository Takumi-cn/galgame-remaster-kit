"""Dependency-light image A/B metrics and labeled comparison sheets.

This is the measurement part of a display-pipeline experiment. It avoids
floating-point arrays: Pillow's ``ImageChops``/``ImageStat`` are enough for
mean absolute difference, PSNR, and a simple edge-energy proxy.

Important methodological note: compare the image that actually reaches the
display, not an intermediate framebuffer. Supersampling pipelines look sharp
in a pre-downsample capture and lose some of that sharpness at scanout.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat

__all__ = [
    "Metrics",
    "compare_images",
    "edge_energy",
    "load_rgb",
    "make_comparison",
    "make_diff_heatmap",
    "normalize_size",
]


@dataclass(frozen=True)
class Metrics:
    width: int
    height: int
    mean_abs_diff: float
    psnr_db: float
    edge_energy_a: float
    edge_energy_b: float
    edge_ratio: float | None
    changed_fraction: float
    max_abs_diff: int
    threshold: int
    mse: float

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


def load_rgb(path: str | Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


def normalize_size(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    if image.size == size:
        return image
    return image.resize(size, Image.Resampling.LANCZOS)


def _apply_region(
    image: Image.Image, region: tuple[int, int, int, int] | None
) -> Image.Image:
    if region is None:
        return image
    x0, y0, x1, y1 = region
    if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
        raise ValueError(f"region {region} is outside image bounds {image.size}")
    return image.crop(region)


def edge_energy(image: Image.Image) -> float:
    """Mean response of a 3x3 edge filter; a rough acutance proxy.

    Use it only to compare images of identical size and content. It rewards
    both real detail and sharpening halos, so pair it with a visual check.
    """
    gray = image.convert("L").filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(gray).mean[0])


def _psnr(diff: Image.Image) -> tuple[float, float]:
    stat = ImageStat.Stat(diff)
    mse = sum(stat.sum2) / (diff.width * diff.height * len(stat.sum2))
    if mse == 0:
        return math.inf, 0.0
    return 10.0 * math.log10((255.0 * 255.0) / mse), mse


def compare_images(
    image_a: Image.Image,
    image_b: Image.Image,
    *,
    normalize: tuple[int, int] | None = None,
    region: tuple[int, int, int, int] | None = None,
    threshold: int = 2,
) -> Metrics:
    a = image_a.convert("RGB")
    b = image_b.convert("RGB")
    if normalize is not None:
        a = normalize_size(a, normalize)
        b = normalize_size(b, normalize)
    if a.size != b.size:
        raise ValueError(
            f"image sizes differ ({a.size} vs {b.size}); pass normalize=WxH"
        )
    a = _apply_region(a, region)
    b = _apply_region(b, region)

    diff = ImageChops.difference(a, b)
    mean_abs = sum(ImageStat.Stat(diff).mean) / 3.0
    psnr, mse = _psnr(diff)

    channels = diff.split()
    max_diff = ImageChops.lighter(
        ImageChops.lighter(channels[0], channels[1]), channels[2]
    )
    histogram = max_diff.histogram()
    changed = sum(histogram[threshold + 1 :]) / (diff.width * diff.height)
    max_abs = max((value for value, count in enumerate(histogram) if count), default=0)
    energy_a = edge_energy(a)
    energy_b = edge_energy(b)
    if energy_a > 0:
        ratio: float | None = energy_b / energy_a
    elif energy_b == 0:
        ratio = 1.0
    else:
        ratio = None

    return Metrics(
        width=a.width,
        height=a.height,
        mean_abs_diff=round(mean_abs, 6),
        psnr_db=round(psnr, 6) if math.isfinite(psnr) else psnr,
        edge_energy_a=round(energy_a, 6),
        edge_energy_b=round(energy_b, 6),
        edge_ratio=round(ratio, 6) if ratio is not None else None,
        changed_fraction=round(changed, 6),
        max_abs_diff=max_abs,
        threshold=threshold,
        mse=round(mse, 6),
    )


def make_comparison(
    image_a: Image.Image,
    image_b: Image.Image,
    output: str | Path,
    *,
    label_a: str = "A",
    label_b: str = "B",
    zoom: int = 1,
    stack: str = "vertical",
) -> Path:
    """Write a labeled side-by-side sheet and return its path."""
    if stack not in {"vertical", "horizontal"}:
        raise ValueError("stack must be 'vertical' or 'horizontal'")
    if zoom < 1:
        raise ValueError("zoom must be >= 1")
    a = image_a.convert("RGB")
    b = image_b.convert("RGB")
    if a.size != b.size:
        raise ValueError("comparison images must have the same size")
    if zoom != 1:
        a = a.resize((a.width * zoom, a.height * zoom), Image.Resampling.NEAREST)
        b = b.resize((b.width * zoom, b.height * zoom), Image.Resampling.NEAREST)

    label_h = 26
    gap = 8
    font = ImageFont.load_default()
    if stack == "vertical":
        canvas = Image.new("RGB", (a.width, a.height * 2 + label_h * 2), (18, 18, 18))
        canvas.paste(a, (0, label_h))
        canvas.paste(b, (0, a.height + label_h * 2))
        draw = ImageDraw.Draw(canvas)
        draw.text((6, 6), label_a, fill=(255, 120, 120), font=font)
        draw.text((6, a.height + label_h + 6), label_b, fill=(120, 255, 160), font=font)
    else:
        canvas = Image.new(
            "RGB", (a.width * 2 + gap, a.height + label_h), (18, 18, 18)
        )
        canvas.paste(a, (0, label_h))
        canvas.paste(b, (a.width + gap, label_h))
        draw = ImageDraw.Draw(canvas)
        draw.text((6, 6), label_a, fill=(255, 120, 120), font=font)
        draw.text((a.width + gap + 6, 6), label_b, fill=(120, 255, 160), font=font)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return out_path


def make_diff_heatmap(
    image_a: Image.Image,
    image_b: Image.Image,
    output: str | Path,
    *,
    amplify: int = 4,
) -> Path:
    """Write an amplified max-channel difference map (grayscale)."""
    if amplify < 1:
        raise ValueError("amplify must be >= 1")
    a = image_a.convert("RGB")
    b = image_b.convert("RGB")
    if a.size != b.size:
        raise ValueError("diff images must have the same size")
    diff = ImageChops.difference(a, b)
    channels = diff.split()
    max_diff = ImageChops.lighter(
        ImageChops.lighter(channels[0], channels[1]), channels[2]
    )
    max_diff = max_diff.point(lambda value: min(255, value * amplify))
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    max_diff.save(out_path)
    return out_path

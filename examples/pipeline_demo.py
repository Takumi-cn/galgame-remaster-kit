"""Compare a direct upscale with a supersampled-then-downscaled chain.

This is a resampling simulation on synthetic placeholder art. It demonstrates
the measurement habit, not a claim about a particular game or upscaler.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from vnremaster.compare import (  # noqa: E402
    compare_images,
    make_comparison,
    make_diff_heatmap,
)
from vnremaster.demo import make_demo_images  # noqa: E402


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "pipeline_out")
    output.mkdir(parents=True, exist_ok=True)

    _before, after = make_demo_images(output)
    with Image.open(after) as handle:
        source = handle.convert("RGB")

    target = (1280, 960)
    direct = source.resize(target, Image.Resampling.LANCZOS)
    intermediate = source.resize((1920, 1440), Image.Resampling.LANCZOS)
    supersampled = intermediate.resize(target, Image.Resampling.LANCZOS)

    metrics = compare_images(direct, supersampled)
    sheet = make_comparison(
        direct,
        supersampled,
        output / "pipeline_compare.png",
        label_a="direct 2x",
        label_b="3x then 2/3 downsample",
    )
    heatmap = make_diff_heatmap(
        direct, supersampled, output / "pipeline_diff.png", amplify=4
    )

    print(f"sheet:   {sheet}")
    print(f"heatmap: {heatmap}")
    print(
        f"mean_abs_diff={metrics.mean_abs_diff:.4f} "
        f"psnr={metrics.psnr_db} dB "
        f"edge={metrics.edge_energy_a:.3f}->{metrics.edge_energy_b:.3f} "
        f"changed={metrics.changed_fraction:.2%}"
    )
    print(
        "The numbers depend on the source and the kernels; inspect the sheet "
        "before drawing a conclusion."
    )


if __name__ == "__main__":
    main()

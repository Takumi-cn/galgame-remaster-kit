import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from vnremaster.compare import (
    compare_images,
    edge_energy,
    make_comparison,
    make_diff_heatmap,
    normalize_size,
)


def solid(size=(64, 64), color=(0, 0, 0)) -> Image.Image:
    return Image.new("RGB", size, color)


def with_square(size=(64, 64), blur: bool = False) -> Image.Image:
    image = solid(size)
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, 44, 44], fill=(255, 255, 255))
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(1.5))
    return image


class CompareMetricsTests(unittest.TestCase):
    def test_identical_images(self):
        metrics = compare_images(solid(), solid())
        self.assertEqual(metrics.mean_abs_diff, 0.0)
        self.assertEqual(metrics.psnr_db, float("inf"))
        self.assertEqual(metrics.edge_energy_a, 0.0)
        self.assertEqual(metrics.edge_ratio, 1.0)
        self.assertEqual(metrics.changed_fraction, 0.0)
        self.assertEqual(metrics.max_abs_diff, 0)

    def test_different_images(self):
        metrics = compare_images(solid(), solid(color=(255, 255, 255)))
        self.assertEqual(metrics.mean_abs_diff, 255.0)
        self.assertEqual(metrics.psnr_db, 0.0)
        self.assertEqual(metrics.changed_fraction, 1.0)
        self.assertEqual(metrics.max_abs_diff, 255)

    def test_threshold(self):
        a = solid()
        b = solid(color=(1, 1, 1))
        self.assertEqual(compare_images(a, b, threshold=2).changed_fraction, 0.0)
        self.assertEqual(compare_images(a, b, threshold=0).changed_fraction, 1.0)

    def test_edge_ratio(self):
        metrics = compare_images(with_square(), with_square(blur=True))
        self.assertIsNotNone(metrics.edge_ratio)
        self.assertLess(metrics.edge_ratio, 1.0)

    def test_normalize(self):
        metrics = compare_images(
            solid((32, 32)), solid((64, 64)), normalize=(80, 60)
        )
        self.assertEqual((metrics.width, metrics.height), (80, 60))

    def test_region(self):
        metrics = compare_images(
            with_square(), with_square(), region=(16, 16, 48, 48)
        )
        self.assertEqual((metrics.width, metrics.height), (32, 32))

    def test_edge_energy_detects_blur(self):
        sharp = edge_energy(with_square())
        blurred = edge_energy(with_square(blur=True))
        self.assertGreater(sharp, blurred)

    def test_size_mismatch_without_normalize(self):
        with self.assertRaises(ValueError):
            compare_images(solid((32, 32)), solid((64, 64)))

    def test_normalize_helper(self):
        image = normalize_size(solid((32, 32)), (48, 48))
        self.assertEqual(image.size, (48, 48))


class ComparisonSheetTests(unittest.TestCase):
    def test_vertical_sheet(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "cmp.png"
            make_comparison(
                with_square(),
                with_square(blur=True),
                out,
                label_a="sharp",
                label_b="blur",
            )
            with Image.open(out) as image:
                self.assertEqual(image.size, (64, 64 * 2 + 52))

    def test_horizontal_zoom(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "cmp.png"
            make_comparison(
                with_square(),
                with_square(),
                out,
                zoom=2,
                stack="horizontal",
            )
            with Image.open(out) as image:
                self.assertEqual(image.size, (64 * 2 * 2 + 8, 64 * 2 + 26))

    def test_diff_heatmap(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "diff.png"
            make_diff_heatmap(with_square(), with_square(blur=True), out, amplify=3)
            self.assertTrue(out.exists())
            with Image.open(out) as image:
                self.assertEqual(image.size, (64, 64))

    def test_rejects_different_sizes(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                make_comparison(
                    solid((32, 32)), solid((64, 64)), Path(temp) / "x.png"
                )


if __name__ == "__main__":
    unittest.main()

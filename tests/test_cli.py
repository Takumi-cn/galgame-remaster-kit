import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from vnremaster.__main__ import main
from vnremaster.pac import PacArchive


def run(*args: str) -> tuple[int, str]:
    with contextlib.redirect_stdout(io.StringIO()) as output:
        code = main(list(args))
    return code, output.getvalue()


class CliTests(unittest.TestCase):
    def test_demo_inspect_verify(self):
        with tempfile.TemporaryDirectory() as temp:
            code, _ = run("demo", temp)
            self.assertEqual(code, 0)
            pac = Path(temp) / "demo.pac"
            self.assertTrue(pac.exists())
            code, output = run("pac", "inspect", str(pac), "--json")
            self.assertEqual(code, 0)
            self.assertIn('"count": 3', output)
            code, _ = run("pac", "verify", str(pac))
            self.assertEqual(code, 0)

    def test_rebuild_and_verify(self):
        with tempfile.TemporaryDirectory() as temp:
            run("demo", temp)
            pac = Path(temp) / "demo.pac"
            archive = PacArchive.from_file(pac)
            replacement = Path(temp) / "replacement.bin"
            replacement.write_bytes(b"x\n")
            out = Path(temp) / "rebuilt.pac"
            code, _ = run(
                "pac",
                "rebuild",
                str(pac),
                "--set",
                f"0={replacement}",
                "--out",
                str(out),
            )
            self.assertEqual(code, 0)
            rebuilt = PacArchive.from_file(out)
            self.assertEqual(rebuilt.read_stream(0), b"x\n")
            self.assertEqual(len(out.read_bytes()), len(archive.data))

    def test_pac_diff_and_stats(self):
        with tempfile.TemporaryDirectory() as temp:
            run("demo", temp)
            pac = Path(temp) / "demo.pac"
            code, output = run("pac", "stats", str(pac), "--json")
            self.assertEqual(code, 0)
            self.assertIn('"count": 3', output)
            code, output = run("pac", "diff", str(pac), str(pac), "--json")
            self.assertEqual(code, 0)
            self.assertIn('"different": false', output)

            replacement = Path(temp) / "replacement.bin"
            replacement.write_bytes(bytes([120, 10]))
            modified = Path(temp) / "modified.pac"
            run(
                "pac",
                "rebuild",
                str(pac),
                "--set",
                f"0={replacement}",
                "--out",
                str(modified),
            )
            code, _ = run(
                "pac", "diff", str(pac), str(modified), "--fail-on-diff"
            )
            self.assertEqual(code, 1)

    def test_glyph_plan_with_font(self):
        fonts = [
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        font = next((path for path in fonts if path.exists()), None)
        if font is None:
            self.skipTest("no system font available")
        map_path = (
            Path(__file__).resolve().parents[1] / "examples" / "demo_map.json"
        )
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "plan.json"
            code, _ = run(
                "glyph",
                "plan",
                "--font",
                str(font),
                "--text",
                "说话门",
                "--candidates",
                str(map_path),
                "--out",
                str(out),
            )
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            self.assertIn('"pairs"', out.read_text(encoding="utf-8"))

    def test_windows_capture_requires_a_target(self):
        with tempfile.TemporaryDirectory() as temp:
            code, _ = run(
                "windows", "capture", "--out", str(Path(temp) / "x.png")
            )
            self.assertEqual(code, 2)

    def test_compare_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            run("demo", temp)
            out = Path(temp) / "cmp.png"
            code, output = run(
                "compare",
                str(Path(temp) / "before.png"),
                str(Path(temp) / "after.png"),
                "--out",
                str(out),
                "--normalize",
                "640x480",
                "--diff-out",
                str(Path(temp) / "diff.png"),
                "--json",
            )
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            self.assertTrue((Path(temp) / "diff.png").exists())
            self.assertIn("mean_abs_diff", output)

    def test_glyph_encode_and_check_without_font(self):
        with tempfile.TemporaryDirectory() as temp:
            map_path = Path(temp) / "map.json"
            map_path.write_text('{"说":"説"}', encoding="utf-8")
            code, output = run(
                "glyph", "encode", "--map", str(map_path), "--text", "说话"
            )
            self.assertEqual(code, 0)
            self.assertEqual(output.strip(), "説话")
            code, output = run(
                "glyph", "check", "--map", str(map_path), "--text", "说话"
            )
            self.assertEqual(code, 0)
            self.assertIn("unmapped", output)

    def test_missing_file_is_reported(self):
        code, _ = run("pac", "inspect", "does-not-exist.pac")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

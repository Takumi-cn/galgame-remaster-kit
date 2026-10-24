import unittest
import zlib

from vnremaster.deflate import (
    ExactSizeError,
    build_exact_size,
    compress_to_exact_size,
)


DATA_SAMPLES = [
    b"",
    b"hello world",
    b"A" * 4096,
    bytes(range(256)) * 16,
    b"The quick brown fox jumps over the lazy dog. " * 50,
]


class ExactSizeTests(unittest.TestCase):
    def test_finished_stream_matches_standard_size(self):
        for data in DATA_SAMPLES:
            standard = zlib.compress(data, 9)
            out = build_exact_size(data, len(standard))
            self.assertIsNotNone(out, f"failed for {len(data)} bytes")
            self.assertEqual(len(out), len(standard))
            self.assertEqual(zlib.decompress(out), data)

    def test_padded_streams_are_complete_and_exact(self):
        data = DATA_SAMPLES[-1]
        base = len(zlib.compress(data, 9))
        for extra in (8, 13, 20, 41, 100, 257):
            target = base + extra
            out = build_exact_size(data, target)
            self.assertIsNotNone(out, f"failed for target {target}")
            self.assertEqual(len(out), target)
            self.assertEqual(zlib.decompress(out), data)
            probe = zlib.decompressobj()
            self.assertEqual(probe.decompress(out), data)
            self.assertTrue(probe.eof, "stream must contain a final block")

    def test_wrapper_searches_parameters(self):
        data = bytes(range(256)) * 32
        target = len(zlib.compress(data, 1)) + 33
        out = compress_to_exact_size(data, target)
        self.assertEqual(len(out), target)
        self.assertEqual(zlib.decompress(out), data)

    def test_impossible_target_raises(self):
        with self.assertRaises(ExactSizeError):
            compress_to_exact_size(b"x" * 1024, 8)

    def test_too_small_target_returns_none(self):
        self.assertIsNone(build_exact_size(b"payload", 4))

    def test_unreachable_gap_returns_none(self):
        # A finished stream is 19 bytes for this payload; 24 is one byte above
        # the smallest sync-flushed wrapper (23) and below the first padded size.
        self.assertIsNone(build_exact_size(b"hello world", 24))


if __name__ == "__main__":
    unittest.main()

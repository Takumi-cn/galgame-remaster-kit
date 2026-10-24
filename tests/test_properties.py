"""Deterministic property-style tests (no external fuzzing dependency)."""

import random
import struct
import unittest
import zlib

from vnremaster.deflate import build_exact_size
from vnremaster.pac import PacArchive


def build_pac(streams: list[bytes], tail: bytes = b"", version: int = 3) -> bytes:
    header = b"PAC\x00" + struct.pack("<II", len(streams), version)
    return header + b"".join(zlib.compress(item, 9) for item in streams) + tail


def random_bytes(rng: random.Random, count: int) -> bytes:
    return bytes(rng.randrange(256) for _ in range(count))


class ExactSizePropertyTests(unittest.TestCase):
    def test_many_payloads_and_targets(self):
        rng = random.Random(20261024)
        for _ in range(8):
            size = rng.choice([0, 1, 7, 64, 257, 1024, 4096])
            data = random_bytes(rng, size)
            base = len(zlib.compress(data, 9))
            for extra in (20, 41, 90):
                target = base + extra
                out = build_exact_size(data, target)
                self.assertIsNotNone(out, f"{size=} {target=}")
                self.assertEqual(len(out), target)
                self.assertEqual(zlib.decompress(out), data)
                probe = zlib.decompressobj()
                probe.decompress(out)
                self.assertTrue(probe.eof)


class PacPropertyTests(unittest.TestCase):
    def test_random_archives_rebuild(self):
        rng = random.Random(9173)
        for _ in range(10):
            count = rng.randrange(1, 7)
            streams = [
                random_bytes(rng, rng.randrange(100, 2001)) for _ in range(count)
            ]
            tail = random_bytes(rng, rng.randrange(0, 24))
            raw = build_pac(streams, tail=tail, version=rng.choice([3, 4]))
            archive = PacArchive.from_bytes(raw)

            target_index = max(
                range(count), key=lambda index: archive.streams[index].csize
            )
            replacement = b"R" * 100
            rebuilt_bytes = archive.rebuild({target_index: replacement})
            self.assertEqual(len(rebuilt_bytes), len(raw))

            rebuilt = PacArchive.from_bytes(rebuilt_bytes)
            self.assertEqual(rebuilt.tail, tail)
            self.assertEqual(rebuilt.read_stream(target_index), replacement)
            for index in range(count):
                old = archive.streams[index]
                new = rebuilt.streams[index]
                self.assertEqual(old.csize, new.csize)
                if index != target_index:
                    self.assertEqual(
                        rebuilt_bytes[new.offset : new.offset + new.csize],
                        raw[old.offset : old.offset + old.csize],
                    )

    def test_malformed_inputs_raise(self):
        rng = random.Random(5150)
        for _ in range(20):
            blob = b"PAC\x00" + random_bytes(rng, rng.randrange(0, 32))
            with self.assertRaises(Exception):
                PacArchive.from_bytes(blob)


if __name__ == "__main__":
    unittest.main()

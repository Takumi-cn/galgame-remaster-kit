import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from vnremaster.pac import (
    PacArchive,
    PacFormatError,
    RepackError,
    write_archive,
)


def build_pac(streams: list[bytes], tail: bytes = b"", version: int = 3) -> bytes:
    header = b"PAC\x00" + struct.pack("<II", len(streams), version)
    return header + b"".join(zlib.compress(item, 9) for item in streams) + tail


class PacParsingTests(unittest.TestCase):
    def test_round_trip_metadata(self):
        streams = [b"A" * 100, bytes(range(256)) * 4, b""]
        raw = build_pac(streams, tail=b"TRAILER\x00", version=4)
        archive = PacArchive.from_bytes(raw)
        self.assertEqual(archive.count, 3)
        self.assertEqual(archive.version, 4)
        self.assertEqual([s.usize for s in archive.streams], [100, 1024, 0])
        self.assertEqual(archive.tail, b"TRAILER\x00")
        self.assertEqual(archive.read_stream(1), streams[1])
        self.assertEqual(archive.tail_offset, len(raw) - len(b"TRAILER\x00"))

    def test_zero_streams(self):
        raw = b"PAC\x00" + struct.pack("<II", 0, 3) + b"tail"
        archive = PacArchive.from_bytes(raw)
        self.assertEqual(archive.count, 0)
        self.assertEqual(archive.tail, b"tail")

    def test_bad_signature(self):
        with self.assertRaises(PacFormatError):
            PacArchive.from_bytes(b"NOPE" + struct.pack("<II", 0, 3))

    def test_truncated_stream(self):
        raw = build_pac([b"hello" * 100])[:-4]
        with self.assertRaises(PacFormatError):
            PacArchive.from_bytes(raw)


class PacRebuildTests(unittest.TestCase):
    def test_exact_size_replacement(self):
        original = [b"A" * 4096, bytes(range(256)) * 16, b"tail-stream"]
        raw = build_pac(original, tail=b"FOOTER")
        archive = PacArchive.from_bytes(raw)
        replacement = b"B" * 1000
        rebuilt_bytes = archive.rebuild({1: replacement})
        self.assertEqual(len(rebuilt_bytes), len(raw))

        rebuilt = PacArchive.from_bytes(rebuilt_bytes)
        self.assertEqual(rebuilt.count, archive.count)
        self.assertEqual(rebuilt.tail, archive.tail)
        self.assertEqual(rebuilt.read_stream(1), replacement)
        for index in (0, 2):
            self.assertEqual(rebuilt.read_stream(index), original[index])
        for old, new in zip(archive.streams, rebuilt.streams):
            self.assertEqual(old.csize, new.csize)
        self.assertEqual(
            rebuilt_bytes[archive.streams[0].offset : archive.streams[0].offset + archive.streams[0].csize],
            raw[archive.streams[0].offset : archive.streams[0].offset + archive.streams[0].csize],
        )

    def test_replacement_too_large(self):
        raw = build_pac([b"small"])
        archive = PacArchive.from_bytes(raw)
        with self.assertRaises(RepackError):
            archive.rebuild({0: bytes(range(256)) * 64})

    def test_bad_index(self):
        archive = PacArchive.from_bytes(build_pac([b"one"]))
        with self.assertRaises(RepackError):
            archive.rebuild({4: b"x"})

    def test_write_archive_in_place_backs_up(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "demo.pac"
            original = build_pac([b"hello"])
            path.write_bytes(original)
            new = build_pac([b"world"])
            write_archive(
                path,
                new,
                in_place=True,
                original=original,
                backup_suffix=".bak",
            )
            self.assertEqual(path.read_bytes(), new)
            self.assertEqual((Path(temp) / "demo.pac.bak").read_bytes(), original)


class PacDiffStatsTests(unittest.TestCase):
    def test_diff_identical(self):
        raw = build_pac([b"one", b"two" * 100], tail=b"tail")
        a = PacArchive.from_bytes(raw)
        b = PacArchive.from_bytes(raw)
        diff = a.diff(b)
        self.assertFalse(diff.different)
        self.assertEqual(diff.changed_count, 0)
        self.assertTrue(diff.tail_equal)

    def test_diff_changed_and_added(self):
        a = PacArchive.from_bytes(build_pac([b"one", b"two"], tail=b"a"))
        b = PacArchive.from_bytes(build_pac([b"one", b"three", b"new"], tail=b"b"))
        diff = a.diff(b)
        self.assertTrue(diff.different)
        self.assertFalse(diff.tail_equal)
        statuses = {item.index: item.status for item in diff.streams}
        self.assertEqual(statuses[0], "same")
        self.assertEqual(statuses[1], "changed")
        self.assertEqual(statuses[2], "only-b")

    def test_diff_without_content_hashing(self):
        a = PacArchive.from_bytes(build_pac([b"payload"]))
        b = PacArchive.from_bytes(build_pac([b"other"]))
        diff = a.diff(b, compare_content=False)
        self.assertEqual(diff.streams[0].status, "changed")
        self.assertIsNone(diff.streams[0].digest_a)

    def test_stats_histogram_and_duplicates(self):
        raw = build_pac([b"x" * 100, b"x" * 100, b"y" * 5000])
        archive = PacArchive.from_bytes(raw)
        stats = archive.stats()
        self.assertEqual(stats.count, 3)
        self.assertEqual(len(stats.duplicates), 1)
        self.assertEqual(stats.duplicates[0][1], (0, 1))
        self.assertEqual(sum(count for _label, count in stats.histogram), 3)
        self.assertGreater(stats.ratio, 0)
        self.assertEqual(stats.largest[0].index, 2)


class PacVerifyTests(unittest.TestCase):
    def test_verify_all_streams(self):
        archive = PacArchive.from_bytes(build_pac([b"a", b"b" * 100]))
        archive.verify()

    def test_verify_detects_corruption(self):
        raw = bytearray(build_pac([b"hello" * 100]))
        raw[-1] ^= 0xFF
        with self.assertRaises(Exception):
            PacArchive.from_bytes(bytes(raw)).verify()


if __name__ == "__main__":
    unittest.main()

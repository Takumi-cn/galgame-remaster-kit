"""Reader/rebuilder for a simple sequential-zlib PAC container.

The container layout handled here is intentionally narrow::

    offset 0   b"PAC\\0"
    offset 4   uint32 little-endian stream count
    offset 8   uint32 little-endian version
    offset 12  stream 0 (a complete zlib stream)
               stream 1
               ...
               stream N-1
               trailing bytes (preserved verbatim)

There is no index: each stream's compressed size is discovered by letting
zlib consume bytes until the stream reaches its final block. This is why a
replacement must be recompressed to the *same* compressed size; see
:mod:`vnremaster.deflate`.

The class also works as a small format-analysis example: it never assumes a
particular game, asset type, or footer.
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .deflate import ExactSizeError, compress_to_exact_size

__all__ = [
    "PacArchive",
    "PacDiff",
    "PacFormatError",
    "PacStats",
    "RepackError",
    "StreamDiff",
    "StreamInfo",
    "sniff",
    "write_archive",
]

SIGNATURE = b"PAC\x00"
HEADER_SIZE = 12
_SCAN_CHUNK = 1 << 20
_MAX_STREAMS = 10_000_000


class PacFormatError(ValueError):
    """The input is not a PAC container this module understands."""


class RepackError(ValueError):
    """A replacement cannot be stored without changing the archive layout."""


@dataclass(frozen=True)
class StreamInfo:
    index: int
    offset: int
    csize: int
    usize: int

    @property
    def ratio(self) -> float:
        return self.csize / self.usize if self.usize else 0.0


@dataclass(frozen=True)
class StreamDiff:
    index: int
    status: str
    csize_a: int | None
    csize_b: int | None
    usize_a: int | None
    usize_b: int | None
    digest_a: str | None = None
    digest_b: str | None = None


@dataclass(frozen=True)
class PacDiff:
    version_a: int
    version_b: int
    count_a: int
    count_b: int
    tail_equal: bool
    streams: tuple[StreamDiff, ...]
    compare_content: bool

    @property
    def different(self) -> bool:
        if self.version_a != self.version_b:
            return True
        if self.count_a != self.count_b:
            return True
        if not self.tail_equal:
            return True
        return any(item.status != "same" for item in self.streams)

    @property
    def changed_count(self) -> int:
        return sum(1 for item in self.streams if item.status != "same")


@dataclass(frozen=True)
class PacStats:
    count: int
    version: int
    total_csize: int
    total_usize: int
    tail_bytes: int
    ratio: float
    largest: tuple[StreamInfo, ...]
    duplicates: tuple[tuple[str, tuple[int, ...], int], ...]
    histogram: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class PacArchive:
    data: bytes
    version: int
    streams: tuple[StreamInfo, ...]
    tail: bytes

    @property
    def count(self) -> int:
        return len(self.streams)

    @property
    def tail_offset(self) -> int:
        if not self.streams:
            return HEADER_SIZE
        last = self.streams[-1]
        return last.offset + last.csize

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> "PacArchive":
        return cls.from_bytes(Path(path).read_bytes())

    @classmethod
    def from_bytes(cls, data: bytes) -> "PacArchive":
        raw = bytes(data)
        if len(raw) < HEADER_SIZE:
            raise PacFormatError("file is smaller than the PAC header")
        if raw[:4] != SIGNATURE:
            raise PacFormatError(
                f"bad signature {raw[:4]!r}; expected {SIGNATURE!r}"
            )
        count, version = struct.unpack_from("<II", raw, 4)
        if count > _MAX_STREAMS:
            raise PacFormatError(f"implausible stream count: {count}")

        view = memoryview(raw)
        streams: list[StreamInfo] = []
        pos = HEADER_SIZE
        for index in range(count):
            if pos >= len(raw):
                raise PacFormatError(f"stream {index} starts past end of file")
            csize, usize = _scan_stream(view, pos)
            if csize <= 0:
                raise PacFormatError(f"stream {index} has zero compressed size")
            streams.append(StreamInfo(index, pos, csize, usize))
            pos += csize

        return cls(
            data=raw,
            version=version,
            streams=tuple(streams),
            tail=raw[pos:],
        )

    def read_stream(self, index: int) -> bytes:
        """Decompress one stream on demand."""
        try:
            info = self.streams[index]
        except IndexError as exc:
            raise IndexError(f"stream index out of range: {index}") from exc
        payload = zlib.decompress(self.data[info.offset : info.offset + info.csize])
        if len(payload) != info.usize:
            raise PacFormatError(
                f"stream {index}: expected {info.usize} bytes, got {len(payload)}"
            )
        return payload

    def verify(self) -> None:
        """Decompress every stream and check the recorded uncompressed sizes."""
        for info in self.streams:
            self.read_stream(info.index)

    def rebuild(self, replacements: Mapping[int, bytes]) -> bytes:
        """Return a new archive with selected streams replaced.

        Every replacement is compressed to the original stream's compressed
        size. All untouched streams are copied byte-for-byte. The resulting
        archive is parsed again and checked before it is returned.
        """
        unknown = sorted(set(replacements) - set(range(self.count)))
        if unknown:
            raise RepackError(f"stream indices out of range: {unknown}")

        parts: list[bytes] = [self.data[:HEADER_SIZE]]
        for info in self.streams:
            if info.index in replacements:
                payload = bytes(replacements[info.index])
                try:
                    parts.append(compress_to_exact_size(payload, info.csize))
                except ExactSizeError as exc:
                    raise RepackError(
                        f"stream {info.index}: {exc}"
                    ) from exc
            else:
                parts.append(
                    self.data[info.offset : info.offset + info.csize]
                )
        parts.append(self.tail)
        out = b"".join(parts)
        self._verify_rebuild(out, replacements)
        return out

    def _verify_rebuild(
        self, out: bytes, replacements: Mapping[int, bytes]
    ) -> None:
        if len(out) != len(self.data):
            raise RepackError(
                f"archive size changed: {len(self.data)} -> {len(out)}"
            )
        rebuilt = PacArchive.from_bytes(out)
        if rebuilt.count != self.count or rebuilt.version != self.version:
            raise RepackError("header/count changed during rebuild")
        if rebuilt.tail != self.tail:
            raise RepackError("trailing bytes changed during rebuild")
        for old, new in zip(self.streams, rebuilt.streams):
            if old.csize != new.csize:
                raise RepackError(f"stream {old.index}: csize changed")
            if old.index in replacements:
                if rebuilt.read_stream(new.index) != bytes(
                    replacements[old.index]
                ):
                    raise RepackError(
                        f"stream {old.index}: replacement round-trip failed"
                    )
            else:
                old_slice = self.data[old.offset : old.offset + old.csize]
                new_slice = out[new.offset : new.offset + new.csize]
                if old_slice != new_slice:
                    raise RepackError(
                        f"stream {old.index}: untouched bytes changed"
                    )

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Write this archive's bytes to *path* (no atomicity guarantees)."""
        target = Path(path)
        target.write_bytes(self.data)
        return target

    def digest(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def stream_digest(self, index: int) -> str:
        return hashlib.sha256(self.read_stream(index)).hexdigest()

    def diff(self, other: "PacArchive", *, compare_content: bool = True) -> PacDiff:
        """Compare stream layout and, optionally, decompressed payloads."""
        total = max(self.count, other.count)
        items: list[StreamDiff] = []
        for index in range(total):
            a = self.streams[index] if index < self.count else None
            b = other.streams[index] if index < other.count else None
            if a is None or b is None:
                items.append(
                    StreamDiff(
                        index=index,
                        status="only-a" if b is None else "only-b",
                        csize_a=a.csize if a else None,
                        csize_b=b.csize if b else None,
                        usize_a=a.usize if a else None,
                        usize_b=b.usize if b else None,
                    )
                )
                continue
            same_layout = (
                a.csize == b.csize
                and self.data[a.offset : a.offset + a.csize]
                == other.data[b.offset : b.offset + b.csize]
            )
            if same_layout:
                items.append(
                    StreamDiff(
                        index=index,
                        status="same",
                        csize_a=a.csize,
                        csize_b=b.csize,
                        usize_a=a.usize,
                        usize_b=b.usize,
                    )
                )
                continue
            digest_a = digest_b = None
            status = "changed"
            if compare_content:
                digest_a = self.stream_digest(index)
                digest_b = other.stream_digest(index)
                if digest_a == digest_b:
                    status = "recompressed"
            items.append(
                StreamDiff(
                    index=index,
                    status=status,
                    csize_a=a.csize,
                    csize_b=b.csize,
                    usize_a=a.usize,
                    usize_b=b.usize,
                    digest_a=digest_a,
                    digest_b=digest_b,
                )
            )
        return PacDiff(
            version_a=self.version,
            version_b=other.version,
            count_a=self.count,
            count_b=other.count,
            tail_equal=self.tail == other.tail,
            streams=tuple(items),
            compare_content=compare_content,
        )

    def stats(self, *, top: int = 10) -> PacStats:
        """Summarise sizes and detect duplicate decompressed payloads."""
        digests: dict[str, list[int]] = {}
        total_usize = 0
        for info in self.streams:
            payload = self.read_stream(info.index)
            total_usize += len(payload)
            digests.setdefault(hashlib.sha256(payload).hexdigest(), []).append(
                info.index
            )
        total_csize = sum(info.csize for info in self.streams)
        duplicates = tuple(
            sorted(
                (
                    (digest, tuple(indices), self.streams[indices[0]].usize)
                    for digest, indices in digests.items()
                    if len(indices) > 1
                ),
                key=lambda item: (-len(item[1]), item[0]),
            )
        )
        largest = tuple(
            sorted(self.streams, key=lambda info: info.csize, reverse=True)[:top]
        )
        buckets = (
            ("<=1 KiB", 1024),
            ("<=4 KiB", 4096),
            ("<=16 KiB", 16384),
            ("<=64 KiB", 65536),
            ("<=256 KiB", 262144),
            ("<=1 MiB", 1048576),
        )
        counts = [0] * (len(buckets) + 1)
        for info in self.streams:
            placed = False
            for pos, (_label, limit) in enumerate(buckets):
                if info.usize <= limit:
                    counts[pos] += 1
                    placed = True
                    break
            if not placed:
                counts[-1] += 1
        histogram = tuple(
            [(label, counts[pos]) for pos, (label, _limit) in enumerate(buckets)]
            + [(">1 MiB", counts[-1])]
        )
        ratio = total_csize / total_usize if total_usize else 0.0
        return PacStats(
            count=self.count,
            version=self.version,
            total_csize=total_csize,
            total_usize=total_usize,
            tail_bytes=len(self.tail),
            ratio=ratio,
            largest=largest,
            duplicates=duplicates,
            histogram=histogram,
        )


def _scan_stream(view: memoryview, pos: int) -> tuple[int, int]:
    """Return ``(compressed_size, uncompressed_size)`` for one zlib stream."""
    obj = zlib.decompressobj()
    fed = 0
    usize = 0
    total = len(view)

    while True:
        if obj.eof:
            break
        chunk = view[pos + fed : min(pos + fed + _SCAN_CHUNK, total)]
        if not chunk:
            raise PacFormatError(
                f"truncated zlib stream at offset {pos} "
                f"(decompressed {usize} bytes)"
            )
        fed += len(chunk)
        try:
            out = obj.decompress(chunk)
        except zlib.error as exc:
            raise PacFormatError(
                f"invalid zlib stream at offset {pos}: {exc}"
            ) from exc
        usize += len(out)

    used = fed - len(obj.unused_data)
    if used <= 0:
        raise PacFormatError(f"stream at offset {pos} consumed no bytes")
    return used, usize


def write_archive(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    in_place: bool = False,
    original: bytes | None = None,
    backup_suffix: str | None = ".bak",
) -> Path:
    """Write archive bytes, optionally replacing an existing file atomically.

    When *in_place* is true and *original* is supplied, a one-time backup is
    created before the replacement (unless a file with the backup name exists).
    """
    target = Path(path)
    payload = bytes(data)
    if not in_place:
        target.write_bytes(payload)
        return target

    if not target.exists():
        raise FileNotFoundError(target)
    if original is None:
        original = target.read_bytes()
    if backup_suffix:
        backup = target.with_name(target.name + backup_suffix)
        if not backup.exists():
            backup.write_bytes(original)

    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return target


def sniff(payload: bytes) -> str:
    """Return a short, human-readable type guess for an asset header."""
    signatures = (
        (b"\x89PNG\r\n\x1a\n", "PNG"),
        (b"\xff\xd8\xff", "JPEG"),
        (b"BM", "BMP"),
        (b"RIFF", "RIFF"),
        (b"PK\x03\x04", "ZIP"),
        (b"OggS", "Ogg"),
        (b"ID3", "MP3/ID3"),
        (b"\x00\x00\x01\x00", "ICO"),
        (b"%PDF", "PDF"),
    )
    for magic, name in signatures:
        if payload.startswith(magic):
            return name
    if payload[:4].isascii() and all(
        32 <= byte < 127 for byte in payload[:4]
    ):
        return "text/unknown"
    return "unknown"

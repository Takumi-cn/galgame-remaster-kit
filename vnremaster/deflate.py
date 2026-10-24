"""Exact-size zlib recompression.

Some legacy asset containers store every asset as a zlib stream whose
compressed size is implied by the offset of the next stream. Replacing an
asset is therefore not enough: the new stream must occupy *exactly* the same
number of bytes, otherwise every following offset shifts.

This module keeps the zlib stream valid while padding it from the inside.
After a ``Z_SYNC_FLUSH`` the deflate stream is byte-aligned; empty DEFLATE
blocks can be appended without changing the decompressed payload:

* an empty stored block costs 5 bytes (3-bit header, alignment, LEN/NLEN);
* an empty fixed-Huffman block costs 10 bits.

The last appended block must set BFINAL. The search below tries both block
orders and a range of block counts, then verifies the result with
``zlib.decompress``.
"""

from __future__ import annotations

import struct
import zlib
from typing import Iterable

__all__ = [
    "ExactSizeError",
    "build_exact_size",
    "compress_to_exact_size",
    "zlib_compress",
]


class ExactSizeError(ValueError):
    """Raised when no zlib stream of the requested size can be produced."""


class _BitWriter:
    __slots__ = ("buf", "bit")

    def __init__(self) -> None:
        self.buf = bytearray()
        self.bit = 0

    def write_bits(self, value: int, n: int) -> None:
        for i in range(n):
            if self.bit == 0:
                self.buf.append(0)
            if (value >> i) & 1:
                self.buf[-1] |= 1 << self.bit
            self.bit = (self.bit + 1) % 8

    def align(self) -> None:
        if self.bit:
            self.bit = 0

    def write_bytes(self, data: bytes) -> None:
        if self.bit != 0:
            raise ValueError("write_bytes requires byte alignment")
        self.buf += data


def _adler32(data: bytes) -> int:
    return zlib.adler32(data) & 0xFFFFFFFF


def _wrap(raw_deflate: bytes, data: bytes) -> bytes:
    # 0x78 0xDA is a valid zlib header (CM=8, FLEVEL=3, FCHECK passes).
    return b"\x78\xda" + raw_deflate + struct.pack(">I", _adler32(data))


def _raw_finished(data: bytes, level: int, mem_level: int, strategy: int) -> bytes:
    obj = zlib.compressobj(level, zlib.DEFLATED, -15, mem_level, strategy)
    return obj.compress(data) + obj.flush(zlib.Z_FINISH)


def _raw_sync(data: bytes, level: int, mem_level: int, strategy: int) -> bytes:
    obj = zlib.compressobj(level, zlib.DEFLATED, -15, mem_level, strategy)
    return obj.compress(data) + obj.flush(zlib.Z_SYNC_FLUSH)


def _padded_exact(
    data: bytes,
    target_size: int,
    level: int,
    mem_level: int,
    strategy: int,
) -> bytes | None:
    """Try to hit *target_size* by appending empty blocks to a sync-flushed stream."""
    raw = _raw_sync(data, level, mem_level, strategy)
    # 2-byte zlib header + deflate bytes + 4-byte Adler-32 trailer.
    base = 2 + len(raw) + 4
    remaining = target_size - base
    if remaining <= 0:
        return None

    def emit(nfix: int, nstored: int, stored_first: bool) -> bytes | None:
        if nfix == 0 and nstored == 0:
            return None
        writer = _BitWriter()
        writer.write_bytes(raw)

        if stored_first:
            for i in range(nstored):
                final = 1 if (i == nstored - 1 and nfix == 0) else 0
                writer.write_bits(final, 1)
                writer.write_bits(0, 2)  # BTYPE=00 (stored)
                writer.align()
                writer.write_bytes(b"\x00\x00\xff\xff")  # LEN=0, NLEN=0xFFFF
            for i in range(nfix):
                writer.write_bits(1 if i == nfix - 1 else 0, 1)
                writer.write_bits(1, 2)  # BTYPE=01 (fixed Huffman)
                writer.write_bits(0, 7)  # end-of-block symbol
        else:
            for i in range(nfix):
                final = 1 if (i == nfix - 1 and nstored == 0) else 0
                writer.write_bits(final, 1)
                writer.write_bits(1, 2)
                writer.write_bits(0, 7)
            for i in range(nstored):
                writer.write_bits(1 if i == nstored - 1 else 0, 1)
                writer.write_bits(0, 2)
                writer.align()
                writer.write_bytes(b"\x00\x00\xff\xff")

        return _wrap(bytes(writer.buf), data)

    # A fixed block costs 10 bits; round up because following blocks may
    # need byte alignment. Search a small window around the theoretical count.
    for nfix in range(0, 65):
        theory = (10 * nfix + 7) // 8
        nstored_center = (remaining - theory) // 5
        for stored_first in (True, False):
            for nstored in range(max(0, nstored_center - 2), nstored_center + 3):
                out = emit(nfix, nstored, stored_first)
                if out is not None and len(out) == target_size:
                    if zlib.decompress(out) == data:
                        return out
    return None


def build_exact_size(
    data: bytes,
    target_size: int,
    *,
    level: int = 9,
    mem_level: int = 9,
    strategy: int = zlib.Z_DEFAULT_STRATEGY,
) -> bytes | None:
    """Return a valid zlib stream of exactly *target_size* bytes, or ``None``.

    The returned stream decompresses to *data*; the check is performed before
    returning.
    """
    if target_size < 8:
        return None

    finished = _wrap(_raw_finished(data, level, mem_level, strategy), data)
    if len(finished) == target_size and zlib.decompress(finished) == data:
        return finished

    padded = _padded_exact(data, target_size, level, mem_level, strategy)
    if padded is not None:
        return padded
    return None


def compress_to_exact_size(
    data: bytes,
    target_size: int,
    *,
    levels: Iterable[int] = range(9, 0, -1),
    mem_levels: Iterable[int] = range(9, 0, -1),
    strategies: Iterable[int] = (0, 1, 2, 3, 4),
) -> bytes:
    """Search encoder settings until an exact-size zlib stream is found.

    Raises:
        ExactSizeError: if the payload cannot be made to fit *target_size*.
    """
    payload = bytes(data)
    for level in levels:
        for mem_level in mem_levels:
            for strategy in strategies:
                out = build_exact_size(
                    payload,
                    target_size,
                    level=level,
                    mem_level=mem_level,
                    strategy=strategy,
                )
                if out is not None:
                    return out
    minimum = len(zlib.compress(payload, 9))
    raise ExactSizeError(
        f"cannot fit payload into {target_size} bytes "
        f"(decompressed {len(payload)} bytes, standard zlib size {minimum} bytes)"
    )


def zlib_compress(data: bytes, level: int = 9) -> bytes:
    """Small convenience wrapper used by the demo/test builders."""
    return zlib.compress(bytes(data), level)

# Exact-size zlib streams: a DEFLATE note

The archive tool needs a zlib stream that decompresses to a new payload **and**
occupies exactly the same number of bytes as the old stream. This note explains
why that is possible, where the constraints are, and how the implementation
searches for a solution.

## 1. Two ways to finish a deflate stream

`zlib.compressobj(..., wbits=-15)` produces raw DEFLATE. There are two relevant
flush modes:

- `Z_FINISH` writes the final block and sets `BFINAL=1`. The stream is complete.
- `Z_SYNC_FLUSH` writes an empty stored block and byte-aligns the output, but
  does not finish the stream. It is intended for streaming, not for a
  self-contained asset.

A complete zlib stream is:

```text
2-byte zlib header | raw DEFLATE blocks | 4-byte Adler-32
```

The hard-coded header `78 DA` is valid (CM=8, FLEVEL=3, FCHECK passes); the
trailer is the Adler-32 of the uncompressed payload.

A finished stream has a minimum size. If the target is larger, the stream must
be padded **inside** the DEFLATE data. Appending bytes after the Adler-32 would
not be part of the stream: the next stream scan would treat them as a new
stream header, or the archive reader would stop at the wrong offset.

## 2. Empty blocks as padding

After a `Z_SYNC_FLUSH` the bitstream is byte-aligned. Empty DEFLATE blocks can
be appended without changing the decompressed payload:

| block type | header | payload | total cost |
|---|---:|---:|---:|
| stored | 3 bits | align + `LEN=0` + `NLEN=0xFFFF` | **5 bytes** |
| fixed Huffman | 3 bits (`BTYPE=01`) + 7-bit end-of-block | none | **10 bits** |

The last appended block must set `BFINAL=1`. Fixed blocks are not byte-aligned
as a group: 10 bits means the next block may start mid-byte. The encoder
therefore tries both orders (fixed blocks first versus stored blocks first) and
a small range of counts, then checks the actual output length.

## 3. Worked example

Take the 11-byte payload `hello world`:

```text
standard zlib stream (Z_FINISH): 19 bytes
sync-flushed wrapper:            23 bytes  (2 + 17 + 4)
```

Target sizes and results:

| target | result | why |
|---:|---|---|
| 19 | exact finished stream | no padding needed |
| 24 | impossible | 23 + 1 byte cannot be formed from 5-byte/10-bit blocks |
| 25 | possible | one fixed empty block (10 bits -> 2 bytes after alignment) |
| 29 | possible | a valid block combination found by the search |
| 39 | possible | a valid block combination found by the search |

The tool never assumes a target is achievable. It returns `None` from the
low-level builder and raises `ExactSizeError` from the parameter search if no
combination works.

## 4. Search strategy

`compress_to_exact_size` tries multiple encoder settings:

- compression levels 9 down to 1;
- `memLevel` 9 down to 1;
- strategies: default, filtered, Huffman-only, RLE, fixed.

For each setting, `build_exact_size` first tries a normal `Z_FINISH` stream. If
its size matches, that is the cleanest result. Otherwise it builds a
sync-flushed stream and searches a small space:

```text
for nfix in 0..64:
    theoretical_bits = ceil(10 * nfix / 8)
    center = (target - sync_size - theoretical_bits) // 5
    for nstored in center-2 .. center+2:
        for order in (fixed-first, stored-first):
            emit and check exact length
```

Every candidate is round-tripped through `zlib.decompress` before being
returned. The total search is bounded and fast for typical targets; a payload
that cannot fit fails early because the compressed size exceeds the target.

## 5. Why the final block matters

A sync-flushed stream is not a complete zlib stream. If it were returned as the
whole replacement, a reader that scans until `eof` would keep consuming the
next stream's bytes. The tool therefore:

- prefers a `Z_FINISH` stream when the target equals its size;
- for padded streams, always makes the last appended block final;
- verifies `decompressobj().eof` in tests.

This is the subtle failure mode that can produce an archive that looks correct
in a hex editor but breaks when the game reads the next asset.

## 6. Failure modes

| symptom | cause | fix |
|---|---|---|
| `ExactSizeError` | payload compresses larger than target | shorten/optimize payload or change layout |
| target unreachable by 1–4 bytes | block granularity | choose a nearby target or a different encoder setting |
| archive reads garbage after replacement | stream lacks `BFINAL` | use the provided builder; never append raw bytes |
| size unchanged but game rejects file | payload semantics changed | verify the payload, not just the length |

## 7. Complexity and limits

- Encoder search is bounded: levels × memLevels × strategies × a small block
  search.
- The builder validates every candidate; it does not trust a length check.
- The archive scanner decompresses one stream at a time while locating
  boundaries; memory is bounded by the largest stream, not the archive size.
- The technique preserves compressed sizes. It does not make a too-large asset
  fit; that requires resizing, re-encoding, or a new container layout.

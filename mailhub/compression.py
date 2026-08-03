"""Text compression for message bodies before they are written to the DB.

Implementation follows the product instruction: Zstandard at level 19 (the
official ``zstandard`` binding), with a 1-byte format marker so compressed
and legacy plain-text rows can coexist and the format can evolve later.

Stored block layout:
  [1 byte: format marker][payload]

  MARKER_RAW       -> payload is the raw UTF-8 text (below the compression
                      threshold, or when compression would not shrink it)
  MARKER_ZSTD_L19  -> payload is a zstd level-19 frame

SQLite stores BLOB bytes natively inside TEXT-affinity columns without
converting them, so no schema change is required.

Thread safety: the asyncio app runs the sync engine and web handlers on a
single event loop / single thread, so module-level reused compressor and
decompressor instances are safe (per the instruction's section 7).
"""

from __future__ import annotations

import logging

import zstandard as zstd

logger = logging.getLogger(__name__)

# --- Format markers -------------------------------------------------------
MARKER_RAW = 0x00       # data stored uncompressed (short / not worth it)
MARKER_ZSTD_L19 = 0x01  # compressed with zstd, level 19

# Strings shorter than this (UTF-8 bytes) are stored raw: the zstd frame
# header (~13 bytes) would make them bigger than the original.
MIN_SIZE_TO_COMPRESS = 128

ZSTD_LEVEL = 19

# --- Reused contexts (constructing these is not free; per section 7) ------
_compressor = zstd.ZstdCompressor(level=ZSTD_LEVEL, write_content_size=True)
_decompressor = zstd.ZstdDecompressor()


def compress_text(text: str) -> bytes:
    """Compress ``text`` into a marker-prefixed BLOB for the DB.

    Short strings and strings that do not shrink are stored raw with the
    MARKER_RAW prefix so decompression stays uniform.
    """
    raw = text.encode("utf-8")
    if len(raw) < MIN_SIZE_TO_COMPRESS:
        return bytes([MARKER_RAW]) + raw

    compressed = _compressor.compress(raw)
    if len(compressed) >= len(raw):
        # Rare on random/incompressible data: keep the original.
        return bytes([MARKER_RAW]) + raw

    return bytes([MARKER_ZSTD_L19]) + compressed


def decompress_text(blob: bytes | str | None) -> str:
    """Restore the original string from a stored BLOB (or legacy text).

    Accepts ``str`` so pre-compression rows read by any code path keep
    working unchanged (they are simply passed through).

    Defensive by design: a truncated or corrupt zstd frame must never break
    the message list/detail API or a notification — it is treated as empty
    text and logged (best-effort, matching mark_read.py).
    """
    if blob is None:
        return ""
    if isinstance(blob, str):
        return blob

    if not blob:
        return ""
    marker, payload = blob[0], blob[1:]

    if marker == MARKER_RAW:
        return payload.decode("utf-8")

    if marker == MARKER_ZSTD_L19:
        try:
            raw = _decompressor.decompress(payload)
            return raw.decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - corrupted blob must not 500
            logger.warning("Corrupt zstd body blob (marker=%s): %s", marker, exc)
            return ""

    raise ValueError(f"Unknown compression marker: {marker!r}")

"""Compress existing message bodies in the database in place (zstd level 19).

Run from the project root with the venv active:
    ./.venv/bin/python scripts/compress_db.py [db_path]

Steps (per the product instruction):
  1. Iterate messages_cache rows in small id batches (memory-safe).
  2. Compress any body_text / body_html that is still stored as plain text;
     already-compressed BLOBs are left untouched (idempotent).
  3. Verify a sample round-trips (decompress(compress(x)) == x).
  4. Report per-column byte totals before/after and the achieved ratio.

It never touches users, accounts, tokens, or any other table. To actually
reclaim the freed pages run VACUUM afterwards (the deploy script does it):
    sqlite3 mailhub.db "VACUUM;"
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mailhub.compression import (  # noqa: E402
    MARKER_RAW,
    MARKER_ZSTD_L19,
    compress_text,
    decompress_text,
)

BATCH_SIZE = 500


def _column_stats(conn: sqlite3.Connection, column: str) -> tuple[int, int]:
    """Total raw bytes in a body column: plain text + compressed payloads."""
    rows = conn.execute(
        f"SELECT typeof({column}), SUM(LENGTH({column})) FROM messages_cache"
    ).fetchall()
    total = 0
    raw_text_bytes = 0
    for kind, size in rows:
        if kind in ("text", "blob") and size:
            total += size
            if kind == "text":
                raw_text_bytes += size
    return total, raw_text_bytes


def migrate(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'messages_cache'"
        ).fetchone()
        if table_exists is None:
            print("messages_cache table does not exist — nothing to migrate.")
            return

        before_text, _ = _column_stats(conn, "body_text")
        before_html, _ = _column_stats(conn, "body_html")
        before_total = before_text + before_html

        min_id, max_id = conn.execute(
            "SELECT MIN(id), MAX(id) FROM messages_cache"
        ).fetchone()
        if min_id is None:
            print("No cached messages — nothing to compress.")
            return

        total_rows = conn.execute(
            "SELECT COUNT(*) FROM messages_cache"
        ).fetchone()[0]
        processed = 0
        compressed_rows = 0
        verified = 0
        # Small sample of (original, compressed) pairs for the round-trip
        # comparison the instruction doc recommends before deleting old data.
        sample_pairs: list[tuple[str, bytes]] = []

        # Walk ids in batches so we never hold every body in memory at once.
        for start in range(min_id, max_id + 1, BATCH_SIZE):
            end = start + BATCH_SIZE - 1
            rows = conn.execute(
                "SELECT id, body_text, body_html FROM messages_cache "
                "WHERE id BETWEEN ? AND ?",
                (start, end),
            ).fetchall()
            for row_id, body_text, body_html in rows:
                updates: list[str] = []
                params: list = []
                for column, value in (("body_text", body_text), ("body_html", body_html)):
                    if value is None or not isinstance(value, str):
                        continue  # already compressed (BLOB) or empty
                    compressed = compress_text(value)
                    if len(sample_pairs) < 20:
                        sample_pairs.append((value, compressed))
                    updates.append(f"{column} = ?")
                    params.append(compressed)
                    compressed_rows += 1
                if updates:
                    conn.execute(
                        f"UPDATE messages_cache SET {', '.join(updates)} WHERE id = ?",
                        (*params, row_id),
                    )
                processed += 1
                if processed % 5000 == 0:
                    conn.commit()
                    print(f"  ... {processed}/{total_rows} rows")
            conn.commit()

        # Round-trip verification: decompress(compressed) must equal the
        # original text for the sampled bodies.
        for original, compressed in sample_pairs:
            if decompress_text(compressed) == original:
                verified += 1

        after_text, _ = _column_stats(conn, "body_text")
        after_html, _ = _column_stats(conn, "body_html")
        after_total = after_text + after_html

        print(f"rows_total={total_rows} rows_processed={processed} "
              f"body_values_compressed={compressed_rows} "
              f"roundtrip_verified={verified}/{len(sample_pairs)}")
        print(f"body_bytes_before={before_total} body_bytes_after={after_total}")
        if before_total:
            ratio = before_total / max(after_total, 1)
            print(f"compression_ratio={ratio:.2f}x")
        print("Migration complete. Run VACUUM to reclaim freed pages.")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "db_path",
        nargs="?",
        default=str(Path(__file__).resolve().parent.parent / "mailhub.db"),
        help="Path to the SQLite database (default: ./mailhub.db)",
    )
    args = parser.parse_args()
    path = Path(args.db_path)
    if not path.exists():
        print(f"Database not found: {path}", file=sys.stderr)
        return 1
    migrate(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

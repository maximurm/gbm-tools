"""GBM binary writer.

Implements GBM_FORMAT_SPEC.md §3-§9. Section content is Snappy-compressed
(raw block format, matching `Yes2/Compress/SnappyInputStream`).

Public API:
    write_gbm(module: GbmModule, path: str | Path) -> None
    encode_gbm(module: GbmModule) -> bytes
"""

from __future__ import annotations

import io
import json
import struct
import time
from pathlib import Path
from typing import IO

import snappy

from .bintex import encode_value_map
from .gbm_module import (
    Backlink,
    BacklinkGroup,
    BookInfo,
    Footnote,
    GbmModule,
    InlineLink,
    Pericope,
    PericopeBlock,
    VersionInfo,
    Xref,
)

MAGIC = b"GBM1"
FORMAT_VERSION = 1
SECTION_INDEX_VERSION = 1


def write_gbm(module: GbmModule, path: str | Path) -> None:
    """Write `module` to `path` as a .gbm file."""
    data = encode_gbm(module)
    Path(path).write_bytes(data)


def encode_gbm(module: GbmModule) -> bytes:
    """Encode `module` and return the full file as bytes."""
    sections: list[tuple[str, bytes, bytes]] = []  # (name, attrs, content)

    # Required sections
    sections.append(_section_version_info(module.version_info))
    sections.append(_section_books_info(module.books))

    # Optional sections (only emitted if non-empty)
    if module.text:
        sections.append(_section_text(module.text))
    if module.pericopes:
        sections.append(_section_pericopes(module.pericopes))
    if module.xrefs:
        sections.append(_section_xrefs(module.xrefs))
    if module.footnotes:
        sections.append(_section_footnotes(module.footnotes))
    if module.inline_links:
        sections.append(_section_inline_links(module.inline_links))
    if module.backlinks:
        sections.append(_section_backlinks(module.backlinks))
    if module.errata_json is not None:
        sections.append(_section_errata(module.errata_json))

    # Build section index
    index_buf = io.BytesIO()
    index_buf.write(struct.pack(">B", SECTION_INDEX_VERSION))
    index_buf.write(struct.pack(">I", len(sections)))

    # Two-pass: compute offsets first
    running_offset = 0
    section_payloads: list[tuple[bytes, bytes]] = []  # (attrs, content_compressed)
    for _name, attrs, content in sections:
        compressed = snappy.compress(content)
        section_payloads.append((attrs, compressed))
        running_offset += len(attrs) + len(compressed)

    cursor = 0
    for (name, attrs, _content_raw), (_a, content_compressed) in zip(
        sections, section_payloads, strict=True
    ):
        name_bytes = name.encode("ascii")
        index_buf.write(struct.pack(">B", len(name_bytes)))
        index_buf.write(name_bytes)
        index_buf.write(struct.pack(">I", cursor))
        index_buf.write(struct.pack(">I", len(attrs)))
        index_buf.write(struct.pack(">I", len(content_compressed)))
        index_buf.write(b"\x00\x00\x00\x00")  # reserved
        cursor += len(attrs) + len(content_compressed)

    section_index_bytes = index_buf.getvalue()

    # Header
    out = io.BytesIO()
    out.write(MAGIC)
    out.write(struct.pack(">B", FORMAT_VERSION))
    out.write(struct.pack(">B", SECTION_INDEX_VERSION))
    out.write(b"\x00\x00")  # reserved
    out.write(struct.pack(">I", len(section_index_bytes)))

    # Section index
    out.write(section_index_bytes)

    # Section payloads in declared order
    for attrs, content_compressed in section_payloads:
        out.write(attrs)
        out.write(content_compressed)

    return out.getvalue()


# ---- Section encoders ----------------------------------------------------------

def _default_attrs() -> bytes:
    return encode_value_map({"encoding": "utf-8", "compression": "snappy"})


def _section_version_info(v: VersionInfo) -> tuple[str, bytes, bytes]:
    buf = io.BytesIO()
    buf.write(struct.pack(">B", 1))  # schema_version
    _write_str16(buf, v.locale)
    _write_str16(buf, v.short_name)
    _write_str16(buf, v.long_name)
    _write_str16(buf, v.description)
    _write_str16(buf, v.copyright)
    buf.write(struct.pack(">B", int(v.corpus)))
    buf.write(struct.pack(">H", v.corpus_version_id))
    buf.write(struct.pack(">I", v.build_unix_seconds or int(time.time())))
    _write_str16(buf, v.builder_version)
    return ("versionInfo", _default_attrs(), buf.getvalue())


def _section_books_info(books: list[BookInfo]) -> tuple[str, bytes, bytes]:
    buf = io.BytesIO()
    buf.write(struct.pack(">B", 1))
    buf.write(struct.pack(">H", len(books)))
    for b in books:
        buf.write(struct.pack(">H", b.book_id))
        _write_str16(buf, b.short_name)
        _write_str16(buf, b.long_name)
        _write_str16(buf, b.abbreviation)
        buf.write(struct.pack(">H", b.chapter_count))
        for vc in b.verse_counts:
            buf.write(struct.pack(">H", vc))
        buf.write(struct.pack(">B", int(b.genre)))
    return ("booksInfo", _default_attrs(), buf.getvalue())


def _section_text(text: dict[tuple[int, int], list[str]]) -> tuple[str, bytes, bytes]:
    # Group by book_id, sorted
    by_book: dict[int, dict[int, list[str]]] = {}
    for (book_id, chapter), verses in text.items():
        by_book.setdefault(book_id, {})[chapter] = verses
    book_ids = sorted(by_book.keys())

    # Build chapter blocks first so we know offsets
    chapter_blobs: dict[int, list[bytes]] = {}  # book_id -> [chapter_blob, ...]
    for book_id in book_ids:
        chapters = by_book[book_id]
        ordered_chapter_nums = sorted(chapters.keys())
        # Validate chapters are contiguous starting at 1
        if ordered_chapter_nums != list(range(1, len(ordered_chapter_nums) + 1)):
            raise ValueError(
                f"book {book_id}: chapters must be 1..N contiguous, got {ordered_chapter_nums}"
            )
        blobs: list[bytes] = []
        for ch in ordered_chapter_nums:
            verses = chapters[ch]
            cb = io.BytesIO()
            cb.write(struct.pack(">H", len(verses)))
            for verse_text in verses:
                vbytes = verse_text.encode("utf-8")
                cb.write(struct.pack(">I", len(vbytes)))
                cb.write(vbytes)
            blobs.append(cb.getvalue())
        chapter_blobs[book_id] = blobs

    # Header sizes
    book_count = len(book_ids)
    header_size = 2  # uint16 book_count
    header_size += book_count * (2 + 4)  # per-book (book_id + book_offset)
    # plus per-book (chapter_count uint16 + chapter_offset uint32 per chapter)
    book_header_sizes: dict[int, int] = {}
    for book_id in book_ids:
        bh = 2 + 4 * len(chapter_blobs[book_id])  # chapter_count + chapter_offset table
        book_header_sizes[book_id] = bh

    # Compute book_offset (offset from start of payload to that book's chapter table)
    book_offset_table: dict[int, int] = {}
    cursor = header_size
    for book_id in book_ids:
        book_offset_table[book_id] = cursor
        cursor += book_header_sizes[book_id]
        cursor += sum(len(b) for b in chapter_blobs[book_id])

    # Compute chapter_offsets per book
    chapter_offset_table: dict[int, list[int]] = {}
    for book_id in book_ids:
        offsets: list[int] = []
        chapter_data_start = book_offset_table[book_id] + book_header_sizes[book_id]
        running = chapter_data_start
        for blob in chapter_blobs[book_id]:
            offsets.append(running)
            running += len(blob)
        chapter_offset_table[book_id] = offsets

    # Now assemble
    out = io.BytesIO()
    out.write(struct.pack(">H", book_count))
    for book_id in book_ids:
        out.write(struct.pack(">H", book_id))
        out.write(struct.pack(">I", book_offset_table[book_id]))
    for book_id in book_ids:
        out.write(struct.pack(">H", len(chapter_blobs[book_id])))
        for off in chapter_offset_table[book_id]:
            out.write(struct.pack(">I", off))
        for blob in chapter_blobs[book_id]:
            out.write(blob)

    return ("text", _default_attrs(), out.getvalue())


def _section_pericopes(items: list[Pericope]) -> tuple[str, bytes, bytes]:
    buf = io.BytesIO()
    buf.write(struct.pack(">B", 1))
    buf.write(struct.pack(">I", len(items)))
    for p in items:
        buf.write(struct.pack(">Q", p.start_vri))
        buf.write(struct.pack(">Q", p.end_vri))
        _write_str16(buf, p.title)
        if len(p.blocks) > 0xFF:
            raise ValueError(f"pericope has too many blocks: {len(p.blocks)} (max 255)")
        buf.write(struct.pack(">B", len(p.blocks)))
        for block in p.blocks:
            buf.write(struct.pack(">B", int(block.kind)))
            _write_str16(buf, block.data)
    return ("pericopes", _default_attrs(), buf.getvalue())


def _section_xrefs(items: list[Xref]) -> tuple[str, bytes, bytes]:
    buf = io.BytesIO()
    buf.write(struct.pack(">B", 1))
    buf.write(struct.pack(">I", len(items)))
    for x in items:
        buf.write(struct.pack(">Q", x.source_vri))
        _write_str16(buf, x.label)
        _write_str16(buf, x.content)
    return ("xrefs", _default_attrs(), buf.getvalue())


def _section_footnotes(items: list[Footnote]) -> tuple[str, bytes, bytes]:
    buf = io.BytesIO()
    buf.write(struct.pack(">B", 1))
    buf.write(struct.pack(">I", len(items)))
    for f in items:
        buf.write(struct.pack(">Q", f.source_vri))
        _write_str16(buf, f.label)
        _write_str16(buf, f.content)
    return ("footnotes", _default_attrs(), buf.getvalue())


def _section_inline_links(items: list[InlineLink]) -> tuple[str, bytes, bytes]:
    buf = io.BytesIO()
    buf.write(struct.pack(">B", 1))
    buf.write(struct.pack(">I", len(items)))
    for link in items:
        buf.write(struct.pack(">Q", link.source_vri))
        buf.write(struct.pack(">H", link.start_offset))
        buf.write(struct.pack(">H", link.length))
        buf.write(struct.pack(">Q", link.target_vri))
        buf.write(struct.pack(">B", int(link.kind)))
    return ("inlineLinks", _default_attrs(), buf.getvalue())


def _section_backlinks(groups: list[BacklinkGroup]) -> tuple[str, bytes, bytes]:
    buf = io.BytesIO()
    buf.write(struct.pack(">B", 1))
    buf.write(struct.pack(">I", len(groups)))
    for g in groups:
        buf.write(struct.pack(">Q", g.target_vri))
        if len(g.sources) > 0xFFFF:
            raise ValueError(
                f"backlink group has too many sources: {len(g.sources)} (max 65535)"
            )
        buf.write(struct.pack(">H", len(g.sources)))
        for src in g.sources:
            buf.write(struct.pack(">Q", src.source_vri))
            buf.write(struct.pack(">B", int(src.kind)))
            buf.write(struct.pack(">B", int(src.verification)))
    return ("backlinks", _default_attrs(), buf.getvalue())


def _section_errata(errata_json: str) -> tuple[str, bytes, bytes]:
    # Validate it parses; we still store as text for on-device readability.
    json.loads(errata_json)
    return ("errata", _default_attrs(), errata_json.encode("utf-8"))


# ---- helpers -------------------------------------------------------------------

def _write_str16(buf: IO[bytes], s: str) -> None:
    encoded = s.encode("utf-8")
    if len(encoded) > 0xFFFF:
        raise ValueError(f"string too long for str16: {len(encoded)} bytes")
    buf.write(struct.pack(">H", len(encoded)))
    buf.write(encoded)

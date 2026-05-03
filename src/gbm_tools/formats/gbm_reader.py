"""GBM binary reader.

Implements GBM_FORMAT_SPEC.md §3-§9 read path. Supports section-on-demand
reads via `GbmReader.read_section()`. The convenience `read_gbm()` function
loads the full module into a `GbmModule` for tests and tooling.
"""

from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import snappy

from .bintex import decode_value_map
from .gbm_module import (
    Backlink,
    BacklinkGroup,
    BookGenre,
    BookInfo,
    Corpus,
    Footnote,
    GbmModule,
    InlineLink,
    LinkKind,
    Pericope,
    PericopeBlock,
    PericopeBlockKind,
    VerificationStatus,
    VersionInfo,
    Xref,
)
from .gbm_writer import FORMAT_VERSION, MAGIC, SECTION_INDEX_VERSION

HEADER_SIZE = 12


@dataclass(frozen=True)
class SectionEntry:
    name: str
    offset: int        # bytes from end-of-section-index to attributes start
    attrs_size: int
    content_size: int


class GbmReader:
    """Random-access reader. Use as a context manager or call .close()."""

    def __init__(self, source: str | Path | bytes):
        if isinstance(source, (str, Path)):
            self._stream: IO[bytes] = open(source, "rb")
            self._owns_stream = True
        else:
            self._stream = io.BytesIO(source)
            self._owns_stream = False
        self._index: dict[str, SectionEntry] | None = None
        self._payload_base: int = 0
        self._format_version: int = 0
        self._section_index_version: int = 0
        self._load_header_and_index()

    # ---- public API ------------------------------------------------------------

    def __enter__(self) -> "GbmReader":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_stream:
            self._stream.close()

    @property
    def format_version(self) -> int:
        return self._format_version

    @property
    def section_names(self) -> list[str]:
        assert self._index is not None
        return list(self._index.keys())

    def has_section(self, name: str) -> bool:
        assert self._index is not None
        return name in self._index

    def read_section(self, name: str) -> tuple[dict, bytes]:
        """Return (attributes_map, decompressed_content) for `name`."""
        assert self._index is not None
        entry = self._index.get(name)
        if entry is None:
            raise KeyError(f"section not found: {name}")
        self._stream.seek(self._payload_base + entry.offset)
        attrs_bytes = _read_exact(self._stream, entry.attrs_size)
        compressed = _read_exact(self._stream, entry.content_size)
        attrs = decode_value_map(attrs_bytes)
        content = snappy.decompress(compressed)
        return attrs, content

    # ---- internals -------------------------------------------------------------

    def _load_header_and_index(self) -> None:
        self._stream.seek(0)
        header = _read_exact(self._stream, HEADER_SIZE)
        if header[:4] != MAGIC:
            raise ValueError(f"not a GBM file: magic {header[:4]!r}")
        self._format_version = header[4]
        self._section_index_version = header[5]
        if self._format_version > FORMAT_VERSION:
            raise ValueError(f"unsupported GBM format_version: {self._format_version}")
        if self._section_index_version > SECTION_INDEX_VERSION:
            raise ValueError(
                f"unsupported section index version: {self._section_index_version}"
            )
        section_index_size = struct.unpack(">I", header[8:12])[0]

        index_bytes = _read_exact(self._stream, section_index_size)
        self._payload_base = HEADER_SIZE + section_index_size
        self._index = _parse_section_index(index_bytes)


def read_gbm(source: str | Path | bytes) -> GbmModule:
    """Eagerly load a .gbm file into a `GbmModule`."""
    with GbmReader(source) as reader:
        version_info = _decode_version_info(reader.read_section("versionInfo")[1])
        books = _decode_books_info(reader.read_section("booksInfo")[1])

        module = GbmModule(version_info=version_info, books=books)

        if reader.has_section("text"):
            module.text = _decode_text(reader.read_section("text")[1])
        if reader.has_section("pericopes"):
            module.pericopes = _decode_pericopes(reader.read_section("pericopes")[1])
        if reader.has_section("xrefs"):
            module.xrefs = _decode_xrefs(reader.read_section("xrefs")[1])
        if reader.has_section("footnotes"):
            module.footnotes = _decode_footnotes(reader.read_section("footnotes")[1])
        if reader.has_section("inlineLinks"):
            module.inline_links = _decode_inline_links(
                reader.read_section("inlineLinks")[1]
            )
        if reader.has_section("backlinks"):
            module.backlinks = _decode_backlinks(reader.read_section("backlinks")[1])
        if reader.has_section("errata"):
            errata_bytes = reader.read_section("errata")[1]
            module.errata_json = errata_bytes.decode("utf-8")
            json.loads(module.errata_json)  # validate structure

        return module


# ---- decoders ------------------------------------------------------------------

def _parse_section_index(data: bytes) -> dict[str, SectionEntry]:
    pos = 0
    version = data[pos]
    pos += 1
    if version > SECTION_INDEX_VERSION:
        raise ValueError(f"section index version too new: {version}")
    count = struct.unpack(">I", data[pos : pos + 4])[0]
    pos += 4
    entries: dict[str, SectionEntry] = {}
    for _ in range(count):
        name_len = data[pos]
        pos += 1
        name = data[pos : pos + name_len].decode("ascii")
        pos += name_len
        offset, attrs_size, content_size = struct.unpack(">III", data[pos : pos + 12])
        pos += 12
        pos += 4  # reserved
        entries[name] = SectionEntry(name, offset, attrs_size, content_size)
    return entries


def _decode_version_info(content: bytes) -> VersionInfo:
    buf = io.BytesIO(content)
    schema = _read_u8(buf)
    if schema != 1:
        raise ValueError(f"versionInfo schema_version {schema} unsupported")
    locale = _read_str16(buf)
    short_name = _read_str16(buf)
    long_name = _read_str16(buf)
    description = _read_str16(buf)
    copyright_ = _read_str16(buf)
    corpus = Corpus(_read_u8(buf))
    corpus_version_id = _read_u16(buf)
    build_unix_seconds = _read_u32(buf)
    builder_version = _read_str16(buf)
    return VersionInfo(
        locale=locale,
        short_name=short_name,
        long_name=long_name,
        description=description,
        copyright=copyright_,
        corpus=corpus,
        corpus_version_id=corpus_version_id,
        build_unix_seconds=build_unix_seconds,
        builder_version=builder_version,
    )


def _decode_books_info(content: bytes) -> list[BookInfo]:
    buf = io.BytesIO(content)
    schema = _read_u8(buf)
    if schema != 1:
        raise ValueError(f"booksInfo schema_version {schema} unsupported")
    book_count = _read_u16(buf)
    books: list[BookInfo] = []
    for _ in range(book_count):
        book_id = _read_u16(buf)
        short_name = _read_str16(buf)
        long_name = _read_str16(buf)
        abbreviation = _read_str16(buf)
        chapter_count = _read_u16(buf)
        verse_counts = [_read_u16(buf) for _ in range(chapter_count)]
        genre = BookGenre(_read_u8(buf))
        books.append(
            BookInfo(
                book_id=book_id,
                short_name=short_name,
                long_name=long_name,
                abbreviation=abbreviation,
                verse_counts=verse_counts,
                genre=genre,
            )
        )
    return books


def _decode_text(content: bytes) -> dict[tuple[int, int], list[str]]:
    buf = io.BytesIO(content)
    book_count = _read_u16(buf)
    book_entries: list[tuple[int, int]] = []
    for _ in range(book_count):
        book_id = _read_u16(buf)
        book_offset = _read_u32(buf)
        book_entries.append((book_id, book_offset))

    out: dict[tuple[int, int], list[str]] = {}
    for book_id, book_offset in book_entries:
        buf.seek(book_offset)
        chapter_count = _read_u16(buf)
        chapter_offsets = [_read_u32(buf) for _ in range(chapter_count)]
        for ch_index, ch_offset in enumerate(chapter_offsets, start=1):
            buf.seek(ch_offset)
            verse_count = _read_u16(buf)
            verses: list[str] = []
            for _ in range(verse_count):
                verse_len = _read_u32(buf)
                verse_bytes = _read_exact(buf, verse_len)
                verses.append(verse_bytes.decode("utf-8"))
            out[(book_id, ch_index)] = verses
    return out


def _decode_pericopes(content: bytes) -> list[Pericope]:
    buf = io.BytesIO(content)
    schema = _read_u8(buf)
    if schema != 1:
        raise ValueError(f"pericopes schema_version {schema} unsupported")
    count = _read_u32(buf)
    out: list[Pericope] = []
    for _ in range(count):
        start = _read_u64(buf)
        end = _read_u64(buf)
        title = _read_str16(buf)
        block_count = _read_u8(buf)
        blocks = [
            PericopeBlock(kind=PericopeBlockKind(_read_u8(buf)), data=_read_str16(buf))
            for _ in range(block_count)
        ]
        out.append(Pericope(start_vri=start, end_vri=end, title=title, blocks=blocks))
    return out


def _decode_xrefs(content: bytes) -> list[Xref]:
    buf = io.BytesIO(content)
    schema = _read_u8(buf)
    if schema != 1:
        raise ValueError(f"xrefs schema_version {schema} unsupported")
    count = _read_u32(buf)
    return [
        Xref(source_vri=_read_u64(buf), label=_read_str16(buf), content=_read_str16(buf))
        for _ in range(count)
    ]


def _decode_footnotes(content: bytes) -> list[Footnote]:
    buf = io.BytesIO(content)
    schema = _read_u8(buf)
    if schema != 1:
        raise ValueError(f"footnotes schema_version {schema} unsupported")
    count = _read_u32(buf)
    return [
        Footnote(source_vri=_read_u64(buf), label=_read_str16(buf), content=_read_str16(buf))
        for _ in range(count)
    ]


def _decode_inline_links(content: bytes) -> list[InlineLink]:
    buf = io.BytesIO(content)
    schema = _read_u8(buf)
    if schema != 1:
        raise ValueError(f"inlineLinks schema_version {schema} unsupported")
    count = _read_u32(buf)
    out: list[InlineLink] = []
    for _ in range(count):
        source_vri = _read_u64(buf)
        start_offset = _read_u16(buf)
        length = _read_u16(buf)
        target_vri = _read_u64(buf)
        kind = LinkKind(_read_u8(buf))
        out.append(
            InlineLink(
                source_vri=source_vri,
                start_offset=start_offset,
                length=length,
                target_vri=target_vri,
                kind=kind,
            )
        )
    return out


def _decode_backlinks(content: bytes) -> list[BacklinkGroup]:
    buf = io.BytesIO(content)
    schema = _read_u8(buf)
    if schema != 1:
        raise ValueError(f"backlinks schema_version {schema} unsupported")
    target_count = _read_u32(buf)
    out: list[BacklinkGroup] = []
    for _ in range(target_count):
        target_vri = _read_u64(buf)
        source_count = _read_u16(buf)
        sources = [
            Backlink(
                source_vri=_read_u64(buf),
                kind=LinkKind(_read_u8(buf)),
                verification=VerificationStatus(_read_u8(buf)),
            )
            for _ in range(source_count)
        ]
        out.append(BacklinkGroup(target_vri=target_vri, sources=sources))
    return out


# ---- low-level helpers ---------------------------------------------------------

def _read_exact(buf: IO[bytes], n: int) -> bytes:
    data = buf.read(n)
    if len(data) != n:
        raise EOFError(f"unexpected EOF: needed {n} bytes, got {len(data)}")
    return data


def _read_u8(buf: IO[bytes]) -> int:
    return _read_exact(buf, 1)[0]


def _read_u16(buf: IO[bytes]) -> int:
    return struct.unpack(">H", _read_exact(buf, 2))[0]


def _read_u32(buf: IO[bytes]) -> int:
    return struct.unpack(">I", _read_exact(buf, 4))[0]


def _read_u64(buf: IO[bytes]) -> int:
    return struct.unpack(">Q", _read_exact(buf, 8))[0]


def _read_str16(buf: IO[bytes]) -> str:
    length = _read_u16(buf)
    return _read_exact(buf, length).decode("utf-8")

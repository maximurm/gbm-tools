"""In-memory representation of a decoded .gbm module.

These dataclasses are the boundary between the binary writer/reader and the
rest of gbm-tools. They are deliberately minimal and mirror the section
schemas in GBM_FORMAT_SPEC.md §7 one-for-one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Corpus(IntEnum):
    UNKNOWN = 0
    BIBLE = 1
    SROD = 2
    EGW = 3


class BookGenre(IntEnum):
    NARRATIVE = 0
    LAW = 1
    POETRY = 2
    PROPHECY = 3
    EPISTLE = 4
    OTHER = 5


class LinkKind(IntEnum):
    QUOTE = 0
    ALLUSION = 1
    REF = 2
    PARALLEL = 3


class VerificationStatus(IntEnum):
    UNVERIFIED = 0
    AUTO = 1
    HUMAN = 2
    DISPUTED = 3


class PericopeBlockKind(IntEnum):
    TEXT = 0
    PARALLEL_REF = 1


@dataclass
class VersionInfo:
    locale: str
    short_name: str
    long_name: str
    description: str
    copyright: str
    corpus: Corpus
    corpus_version_id: int
    build_unix_seconds: int
    builder_version: str


@dataclass
class BookInfo:
    book_id: int
    short_name: str
    long_name: str
    abbreviation: str
    verse_counts: list[int]  # length == chapter_count
    genre: BookGenre = BookGenre.OTHER

    @property
    def chapter_count(self) -> int:
        return len(self.verse_counts)


@dataclass
class PericopeBlock:
    kind: PericopeBlockKind
    data: str


@dataclass
class Pericope:
    start_vri: int
    end_vri: int
    title: str
    blocks: list[PericopeBlock] = field(default_factory=list)


@dataclass
class Xref:
    source_vri: int
    label: str
    content: str


@dataclass
class Footnote:
    source_vri: int
    label: str
    content: str


@dataclass
class InlineLink:
    source_vri: int
    start_offset: int
    length: int
    target_vri: int
    kind: LinkKind = LinkKind.REF


@dataclass
class Backlink:
    source_vri: int
    kind: LinkKind = LinkKind.REF
    verification: VerificationStatus = VerificationStatus.UNVERIFIED


@dataclass
class BacklinkGroup:
    target_vri: int
    sources: list[Backlink] = field(default_factory=list)


@dataclass
class GbmModule:
    """All decodable contents of a .gbm file."""

    version_info: VersionInfo
    books: list[BookInfo]
    # text[(book_id, chapter_1based)] -> list of verse strings (1-based index)
    text: dict[tuple[int, int], list[str]] = field(default_factory=dict)
    pericopes: list[Pericope] = field(default_factory=list)
    xrefs: list[Xref] = field(default_factory=list)
    footnotes: list[Footnote] = field(default_factory=list)
    inline_links: list[InlineLink] = field(default_factory=list)
    backlinks: list[BacklinkGroup] = field(default_factory=list)
    errata_json: str | None = None

    def get_verse(self, book_id: int, chapter: int, verse: int) -> str:
        verses = self.text[(book_id, chapter)]
        return verses[verse - 1]

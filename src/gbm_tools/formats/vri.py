"""VRI (Versioned Reference Index) — 64-bit verse identifier.

Bit layout (big-endian unsigned 64-bit integer):

    bits 63..56  corpus_id     (8-bit, 0–255)
    bits 55..40  version_id    (16-bit, 0–65535)
    bits 39..28  book_id       (12-bit, 0–4095)
    bits 27..16  chapter/page  (12-bit, 0–4095)
    bits 15..0   verse/para    (16-bit, 0–65535)

Reserved corpus IDs:
    0 = unknown / legacy / unresolved
    1 = Bible
    2 = Shepherd's Rod (SRod)
    3 = Ellen G. White (EGW)

The lower 32 bits of any VRI form a valid ARI for the (corpus, version)
implied by the upper 32 bits. See goldenBowl/app/Util/Ari.php.

Source of truth: docs/workspace/GBM_FORMAT_SPEC.md §2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Reserved corpus IDs (must match all 4 platform implementations)
CORPUS_UNKNOWN: Final[int] = 0
CORPUS_BIBLE: Final[int] = 1
CORPUS_SROD: Final[int] = 2
CORPUS_EGW: Final[int] = 3

# Field maxima
MAX_CORPUS: Final[int] = 0xFF      # 255
MAX_VERSION: Final[int] = 0xFFFF   # 65535
MAX_BOOK: Final[int] = 0xFFF       # 4095
MAX_CHAPTER: Final[int] = 0xFFF    # 4095
MAX_VERSE: Final[int] = 0xFFFF     # 65535


@dataclass(frozen=True, slots=True)
class VriParts:
    corpus: int
    version: int
    book: int
    chapter: int
    verse: int


def encode(corpus: int, version: int, book: int, chapter: int, verse: int) -> int:
    """Encode (corpus, version, book, chapter, verse) as a 64-bit unsigned VRI."""
    _validate(corpus, version, book, chapter, verse)
    return (
        ((corpus & MAX_CORPUS) << 56)
        | ((version & MAX_VERSION) << 40)
        | ((book & MAX_BOOK) << 28)
        | ((chapter & MAX_CHAPTER) << 16)
        | (verse & MAX_VERSE)
    )


def decode(vri: int) -> VriParts:
    """Decode a 64-bit VRI into its five components."""
    if vri < 0 or vri > 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"VRI out of 64-bit range: {vri}")
    return VriParts(
        corpus=(vri >> 56) & MAX_CORPUS,
        version=(vri >> 40) & MAX_VERSION,
        book=(vri >> 28) & MAX_BOOK,
        chapter=(vri >> 16) & MAX_CHAPTER,
        verse=vri & MAX_VERSE,
    )


def encode_from_ari(corpus: int, version: int, ari: int) -> int:
    """Build a VRI from a 32-bit ARI plus (corpus, version) prefix.

    The lower 32 bits of the resulting VRI are the ARI verbatim.
    """
    if ari < 0 or ari > 0xFFFFFFFF:
        raise ValueError(f"ARI out of 32-bit range: {ari}")
    if corpus < 0 or corpus > MAX_CORPUS:
        raise ValueError(f"corpus out of range: {corpus}")
    if version < 0 or version > MAX_VERSION:
        raise ValueError(f"version out of range: {version}")
    return ((corpus & MAX_CORPUS) << 56) | ((version & MAX_VERSION) << 40) | ari


def to_ari(vri: int) -> int:
    """Drop corpus + version prefix; return the lower 32-bit ARI."""
    return vri & 0xFFFFFFFF


def _validate(corpus: int, version: int, book: int, chapter: int, verse: int) -> None:
    if not 0 <= corpus <= MAX_CORPUS:
        raise ValueError(f"corpus out of range: {corpus}")
    if not 0 <= version <= MAX_VERSION:
        raise ValueError(f"version out of range: {version}")
    if not 0 <= book <= MAX_BOOK:
        raise ValueError(f"book out of range: {book}")
    if not 0 <= chapter <= MAX_CHAPTER:
        raise ValueError(f"chapter out of range: {chapter}")
    if not 0 <= verse <= MAX_VERSE:
        raise ValueError(f"verse out of range: {verse}")

"""Tests for VRI 64-bit encoding/decoding.

Cross-platform parity: identical inputs MUST produce identical 64-bit outputs
on PHP, Kotlin, Swift, and Python implementations. The reference vectors
below are duplicated verbatim in:
    - goldenBowl/tests/Unit/VriTest.php
    - Biblary/app/.../util/VriTest.kt
    - Alkitab/.../VriTests.swift
"""

from __future__ import annotations

import pytest

from gbm_tools.formats import vri


# (corpus, version, book, chapter, verse) -> expected uint64
PARITY_VECTORS: list[tuple[tuple[int, int, int, int, int], int]] = [
    # Bible KJV Genesis 1:1
    ((1, 1, 1, 1, 1), 0x01_0001_001_001_0001),
    # SRod 1SC chapter 1, paragraph 1 (book=1, ch=1, v=1)
    ((2, 1, 1, 1, 1), 0x02_0001_001_001_0001),
    # EGW Great Controversy
    ((3, 1, 1, 1, 1), 0x03_0001_001_001_0001),
    # Maxima — boundary
    ((255, 0xFFFF, 0xFFF, 0xFFF, 0xFFFF), 0xFF_FFFF_FFF_FFF_FFFF),
    # Zero corpus (legacy / unresolved)
    ((0, 0, 0, 0, 0), 0),
]


@pytest.mark.parametrize("parts,expected", PARITY_VECTORS)
def test_encode_parity(parts: tuple[int, int, int, int, int], expected: int) -> None:
    assert vri.encode(*parts) == expected


@pytest.mark.parametrize("parts,expected", PARITY_VECTORS)
def test_decode_parity(parts: tuple[int, int, int, int, int], expected: int) -> None:
    decoded = vri.decode(expected)
    assert (decoded.corpus, decoded.version, decoded.book,
            decoded.chapter, decoded.verse) == parts


def test_round_trip_random_sample() -> None:
    samples = [
        (1, 100, 40, 28, 19),    # Bible Matthew 28:19
        (2, 1, 5, 7, 47),        # SRod book 5 chapter 7 paragraph 47
        (3, 5, 12, 100, 3),
    ]
    for parts in samples:
        v = vri.encode(*parts)
        d = vri.decode(v)
        assert (d.corpus, d.version, d.book, d.chapter, d.verse) == parts


def test_encode_from_ari_preserves_lower_32() -> None:
    # ARI: book=40 (1-byte), chapter=28, verse=19 → 0x28_1C_0013
    ari = (40 << 24) | (28 << 16) | 19
    v = vri.encode_from_ari(corpus=1, version=100, ari=ari)
    assert vri.to_ari(v) == ari
    assert (v >> 56) == 1
    assert ((v >> 40) & 0xFFFF) == 100


def test_to_ari_drops_prefix() -> None:
    v = vri.encode(corpus=2, version=1, book=1, chapter=1, verse=1)
    ari_part = vri.to_ari(v)
    assert ari_part == ((1 << 28) | (1 << 16) | 1)


def test_validation_rejects_oversized_corpus() -> None:
    with pytest.raises(ValueError, match="corpus"):
        vri.encode(256, 0, 0, 0, 0)


def test_validation_rejects_oversized_book() -> None:
    with pytest.raises(ValueError, match="book"):
        vri.encode(1, 0, 4096, 0, 0)


def test_validation_rejects_oversized_verse() -> None:
    with pytest.raises(ValueError, match="verse"):
        vri.encode(1, 0, 0, 0, 65536)


def test_validation_rejects_negative() -> None:
    with pytest.raises(ValueError):
        vri.encode(-1, 0, 0, 0, 0)


def test_decode_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        vri.decode(-1)
    with pytest.raises(ValueError):
        vri.decode(0x1_0000_0000_0000_0000)  # 65 bits


def test_corpus_constants() -> None:
    assert vri.CORPUS_UNKNOWN == 0
    assert vri.CORPUS_BIBLE == 1
    assert vri.CORPUS_SROD == 2
    assert vri.CORPUS_EGW == 3

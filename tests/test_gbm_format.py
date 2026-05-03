"""Round-trip and edge-case tests for the GBM binary writer/reader."""

from __future__ import annotations

import json

import pytest

from gbm_tools.formats import (
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
    encode,
    encode_gbm,
    read_gbm,
    write_gbm,
)
from gbm_tools.formats.bintex import decode_value_map, encode_value_map
from gbm_tools.formats.gbm_reader import GbmReader


def _tiny_module(*, with_optionals: bool = False) -> GbmModule:
    vi = VersionInfo(
        locale="en",
        short_name="KJV",
        long_name="King James Version",
        description="The KJV (test fixture)",
        copyright="Public Domain",
        corpus=Corpus.BIBLE,
        corpus_version_id=1,
        build_unix_seconds=1_700_000_000,
        builder_version="gbm-tools 0.1.0",
    )
    books = [
        BookInfo(
            book_id=1,
            short_name="Genesis",
            long_name="The First Book of Moses, Called Genesis",
            abbreviation="Gen",
            verse_counts=[3, 2],  # ch 1: 3 verses, ch 2: 2 verses
            genre=BookGenre.NARRATIVE,
        ),
        BookInfo(
            book_id=2,
            short_name="Exodus",
            long_name="The Second Book of Moses, Called Exodus",
            abbreviation="Exo",
            verse_counts=[1],
            genre=BookGenre.NARRATIVE,
        ),
    ]
    text: dict[tuple[int, int], list[str]] = {
        (1, 1): [
            "In the beginning God created the heaven and the earth.",
            "And the earth was without form, and void; @9darkness@7 was upon the face of the deep.",
            "And the Spirit of God moved upon the face of the waters.",
        ],
        (1, 2): [
            "Thus the heavens and the earth were finished, and all the host of them.",
            "And on the seventh day God ended his work which he had made.",
        ],
        (2, 1): [
            "Now these are the names of the children of Israel, which came into Egypt.",
        ],
    }
    module = GbmModule(version_info=vi, books=books, text=text)
    if with_optionals:
        module.pericopes = [
            Pericope(
                start_vri=encode(1, 1, 1, 1, 1),
                end_vri=encode(1, 1, 1, 1, 3),
                title="The Creation",
                blocks=[
                    PericopeBlock(PericopeBlockKind.TEXT, "Genesis 1 — opening"),
                    PericopeBlock(PericopeBlockKind.PARALLEL_REF, "John 1:1-3"),
                ],
            )
        ]
        module.xrefs = [
            Xref(source_vri=encode(1, 1, 1, 1, 1), label="a", content="Heb 11:3"),
        ]
        module.footnotes = [
            Footnote(source_vri=encode(1, 1, 1, 1, 2), label="b", content="Or 'wind of God'."),
        ]
        module.inline_links = [
            InlineLink(
                source_vri=encode(2, 1, 1, 1, 1),  # SRod citation
                start_offset=10,
                length=14,
                target_vri=encode(1, 1, 1, 1, 1),  # → Genesis 1:1
                kind=LinkKind.QUOTE,
            )
        ]
        module.backlinks = [
            BacklinkGroup(
                target_vri=encode(1, 1, 1, 1, 1),
                sources=[
                    Backlink(
                        source_vri=encode(2, 1, 1, 1, 1),
                        kind=LinkKind.QUOTE,
                        verification=VerificationStatus.HUMAN,
                    )
                ],
            )
        ]
        module.errata_json = json.dumps(
            {
                "schema_version": 1,
                "base_module_hash": "sha256:" + "0" * 64,
                "patches": [],
            }
        )
    return module


# ---- header & magic ------------------------------------------------------------

def test_header_has_magic_and_version() -> None:
    module = _tiny_module()
    data = encode_gbm(module)
    assert data[:4] == b"GBM1"
    assert data[4] == 1  # format_version
    assert data[5] == 1  # section_index_version


def test_reader_rejects_wrong_magic() -> None:
    bad = b"NOPE" + b"\x00" * 100
    with pytest.raises(ValueError, match="not a GBM file"):
        GbmReader(bad)


# ---- bintex round-trip ---------------------------------------------------------

def test_bintex_round_trip_all_types() -> None:
    items = {
        "u8": 7,
        "u16": 1_000,
        "u32": 100_000,
        "u64": 2**40,
        "neg": -42,
        "name": "Genesis",
        "encoding": "utf-8",
    }
    encoded = encode_value_map(items)
    decoded = decode_value_map(encoded)
    assert decoded == items


# ---- module round-trip ---------------------------------------------------------

def test_round_trip_minimal() -> None:
    module = _tiny_module()
    data = encode_gbm(module)
    loaded = read_gbm(data)

    assert loaded.version_info.short_name == "KJV"
    assert loaded.version_info.corpus == Corpus.BIBLE
    assert loaded.version_info.build_unix_seconds == 1_700_000_000
    assert len(loaded.books) == 2
    assert loaded.books[0].long_name.startswith("The First Book")
    assert loaded.books[0].verse_counts == [3, 2]
    assert loaded.books[1].verse_counts == [1]
    assert loaded.text[(1, 1)][0].startswith("In the beginning")
    assert "@9darkness@7" in loaded.text[(1, 1)][1]
    assert loaded.text[(2, 1)] == [
        "Now these are the names of the children of Israel, which came into Egypt."
    ]
    assert loaded.pericopes == []
    assert loaded.xrefs == []
    assert loaded.errata_json is None


def test_round_trip_with_all_optional_sections() -> None:
    module = _tiny_module(with_optionals=True)
    data = encode_gbm(module)
    loaded = read_gbm(data)

    assert len(loaded.pericopes) == 1
    assert loaded.pericopes[0].title == "The Creation"
    assert loaded.pericopes[0].blocks[1].kind == PericopeBlockKind.PARALLEL_REF
    assert loaded.xrefs[0].content == "Heb 11:3"
    assert loaded.footnotes[0].label == "b"
    assert loaded.inline_links[0].target_vri == encode(1, 1, 1, 1, 1)
    assert loaded.inline_links[0].kind == LinkKind.QUOTE
    assert loaded.backlinks[0].sources[0].verification == VerificationStatus.HUMAN
    assert loaded.errata_json is not None
    assert json.loads(loaded.errata_json)["schema_version"] == 1


def test_get_verse_helper() -> None:
    module = _tiny_module()
    loaded = read_gbm(encode_gbm(module))
    assert loaded.get_verse(1, 1, 1).startswith("In the beginning")
    assert loaded.get_verse(1, 2, 2).startswith("And on the seventh day")
    assert loaded.get_verse(2, 1, 1).startswith("Now these are the names")


# ---- random-access reader ------------------------------------------------------

def test_reader_lists_sections_and_lazy_reads(tmp_path) -> None:
    module = _tiny_module(with_optionals=True)
    path = tmp_path / "tiny.gbm"
    write_gbm(module, path)

    with GbmReader(path) as reader:
        # required first
        assert reader.section_names[0] == "versionInfo"
        assert reader.section_names[1] == "booksInfo"
        # all sections accessible
        for name in ("text", "pericopes", "xrefs", "footnotes",
                     "inlineLinks", "backlinks", "errata"):
            assert reader.has_section(name)
            attrs, content = reader.read_section(name)
            assert attrs["encoding"] == "utf-8"
            assert attrs["compression"] == "snappy"
            assert isinstance(content, bytes)
            assert len(content) > 0


def test_section_on_demand_does_not_decompress_others(tmp_path) -> None:
    """Spot-check that read_section is independent — calling one does not
    require parsing the others."""
    module = _tiny_module(with_optionals=True)
    path = tmp_path / "tiny.gbm"
    write_gbm(module, path)

    with GbmReader(path) as reader:
        attrs, content = reader.read_section("xrefs")
        assert attrs["compression"] == "snappy"
        assert len(content) > 0
        # And again, out of order — must succeed
        _attrs, content2 = reader.read_section("versionInfo")
        assert content2[0] == 1  # schema_version


# ---- omits empty optional sections --------------------------------------------

def test_no_optional_sections_when_empty() -> None:
    module = _tiny_module()
    with GbmReader(encode_gbm(module)) as reader:
        assert reader.has_section("versionInfo")
        assert reader.has_section("booksInfo")
        assert reader.has_section("text")
        for name in ("pericopes", "xrefs", "footnotes",
                     "inlineLinks", "backlinks", "errata"):
            assert not reader.has_section(name), f"{name} should not be emitted when empty"


# ---- errata validation ---------------------------------------------------------

def test_errata_invalid_json_rejected() -> None:
    module = _tiny_module()
    module.errata_json = "{not valid json"
    with pytest.raises(json.JSONDecodeError):
        encode_gbm(module)

"""Tests for the gbm-diff comparator (Phase C6)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from gbm_tools.diff import diff_modules, write_diff
from gbm_tools.formats import (
    Backlink,
    BacklinkGroup,
    BookGenre,
    BookInfo,
    Corpus,
    GbmModule,
    InlineLink,
    LinkKind,
    VerificationStatus,
    VersionInfo,
    encode,
    encode_gbm,
)


def _base_module() -> GbmModule:
    vi = VersionInfo(
        locale="en",
        short_name="KJV",
        long_name="King James Version",
        description="d",
        copyright="PD",
        corpus=Corpus.BIBLE,
        corpus_version_id=1,
        build_unix_seconds=1_700_000_000,
        builder_version="gbm-tools 0.1.0",
    )
    books = [
        BookInfo(book_id=1, short_name="Genesis", long_name="Genesis",
                 abbreviation="Gen", verse_counts=[3], genre=BookGenre.NARRATIVE),
    ]
    text = {(1, 1): ["a", "b", "c"]}
    return GbmModule(version_info=vi, books=books, text=text)


def _write(tmp_path, name: str, module: GbmModule):
    p = tmp_path / name
    p.write_bytes(encode_gbm(module))
    return p


def test_identical_modules_silent(tmp_path) -> None:
    a = _write(tmp_path, "a.gbm", _base_module())
    b = _write(tmp_path, "b.gbm", _base_module())
    patch = diff_modules(a, b)
    assert patch["severity"] == "silent"
    # only the metadata bookkeeping (or none) — no verse_changed entries
    assert not any(c["kind"] == "verse_changed" for c in patch["changes"])
    assert patch["old_sha256"] == patch["new_sha256"]


def test_verse_change_is_notify(tmp_path) -> None:
    mod_a = _base_module()
    mod_b = _base_module()
    mod_b.text[(1, 1)] = ["a", "b CHANGED", "c"]
    a = _write(tmp_path, "a.gbm", mod_a)
    b = _write(tmp_path, "b.gbm", mod_b)
    patch = diff_modules(a, b)
    assert patch["severity"] == "notify"
    verse_changes = [c for c in patch["changes"] if c["kind"] == "verse_changed"]
    assert len(verse_changes) == 1
    assert verse_changes[0]["ref"] == "1.1:2"


def test_book_added_is_blocking(tmp_path) -> None:
    mod_a = _base_module()
    mod_b = _base_module()
    mod_b.books.append(BookInfo(book_id=2, short_name="Exodus", long_name="Exodus",
                                abbreviation="Exo", verse_counts=[1],
                                genre=BookGenre.NARRATIVE))
    mod_b.text[(2, 1)] = ["x"]
    a = _write(tmp_path, "a.gbm", mod_a)
    b = _write(tmp_path, "b.gbm", mod_b)
    patch = diff_modules(a, b)
    assert patch["severity"] == "blocking"
    assert any(c["kind"] == "books_added" and c["book_ids"] == [2]
               for c in patch["changes"])


def test_backlink_added_is_silent(tmp_path) -> None:
    mod_a = _base_module()
    mod_b = _base_module()
    mod_b.backlinks = [BacklinkGroup(
        target_vri=encode(1, 1, 1, 1, 1),
        sources=[Backlink(source_vri=encode(1, 1, 1, 1, 2),
                          kind=LinkKind.REF,
                          verification=VerificationStatus.AUTO)],
    )]
    a = _write(tmp_path, "a.gbm", mod_a)
    b = _write(tmp_path, "b.gbm", mod_b)
    patch = diff_modules(a, b)
    assert patch["severity"] == "silent"
    assert any(c["kind"] == "backlink_added" for c in patch["changes"])


def test_write_diff_emits_file(tmp_path) -> None:
    mod_a = _base_module()
    mod_b = _base_module()
    mod_b.text[(1, 1)] = ["a", "b!", "c"]
    a = _write(tmp_path, "a.gbm", mod_a)
    b = _write(tmp_path, "b.gbm", mod_b)
    out = tmp_path / "patch.json"
    patch = write_diff(a, b, out, module_id="kjv")
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded == patch
    assert loaded["module_id"] == "kjv"
    assert loaded["severity"] == "notify"

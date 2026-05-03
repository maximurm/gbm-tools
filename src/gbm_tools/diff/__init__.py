"""Two-revision .gbm comparator + errata patch generator (Phase C6).

Compares two .gbm files (rev_a, rev_b) and emits an errata-patch JSON
describing the changes that would transform rev_a into rev_b. The patch
is a content-aware diff (not a byte diff): it walks the decoded
``GbmModule`` sections from ``read_gbm()``.

Severity classification (per GBM_FORMAT_SPEC.md §9.5 errata schema):

    silent    → metadata-only / additive backlinks / additive inline links
    notify    → text content changed in any verse
    blocking  → structural change (book added/removed, corpus changed)

The returned dict is JSON-serialisable. ``write_diff()`` is a thin
helper that serialises the result to disk.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from ..formats.gbm_module import GbmModule
from ..formats.gbm_reader import read_gbm

__all__ = ["diff_modules", "write_diff"]

_SEVERITY_RANK = {"silent": 0, "notify": 1, "blocking": 2}


def _max_sev(*severities: str) -> str:
    return max(severities, key=_SEVERITY_RANK.__getitem__)


def diff_modules(
    rev_a: str | Path,
    rev_b: str | Path,
    *,
    module_id: str | None = None,
) -> dict[str, Any]:
    """Compare two .gbm files; return an errata-patch dict."""
    rev_a_path = Path(rev_a)
    rev_b_path = Path(rev_b)
    bytes_a = rev_a_path.read_bytes()
    bytes_b = rev_b_path.read_bytes()
    sha_a = hashlib.sha256(bytes_a).hexdigest()
    sha_b = hashlib.sha256(bytes_b).hexdigest()

    mod_a = read_gbm(bytes_a)
    mod_b = read_gbm(bytes_b)

    changes: list[dict[str, Any]] = []
    severity = "silent"

    if mod_a.version_info.corpus != mod_b.version_info.corpus:
        changes.append({
            "kind": "corpus_changed",
            "from": int(mod_a.version_info.corpus),
            "to": int(mod_b.version_info.corpus),
        })
        severity = _max_sev(severity, "blocking")

    books_a = {b.book_id: b for b in mod_a.books}
    books_b = {b.book_id: b for b in mod_b.books}
    added = sorted(set(books_b) - set(books_a))
    removed = sorted(set(books_a) - set(books_b))
    if added:
        changes.append({"kind": "books_added", "book_ids": added})
        severity = _max_sev(severity, "blocking")
    if removed:
        changes.append({"kind": "books_removed", "book_ids": removed})
        severity = _max_sev(severity, "blocking")

    text_changes = _diff_text(mod_a, mod_b)
    if text_changes:
        changes.extend(text_changes)
        severity = _max_sev(severity, "notify")

    bl_changes = _diff_backlinks(mod_a, mod_b)
    if bl_changes:
        changes.extend(bl_changes)

    il_changes = _diff_inline_links(mod_a, mod_b)
    if il_changes:
        changes.extend(il_changes)
        if any(c["kind"] == "inline_link_removed" for c in il_changes):
            severity = _max_sev(severity, "notify")

    if mod_a.version_info.short_name != mod_b.version_info.short_name:
        changes.append({
            "kind": "short_name_changed",
            "from": mod_a.version_info.short_name,
            "to": mod_b.version_info.short_name,
        })

    return {
        "spec_version": 1,
        "module_id": module_id or mod_b.version_info.short_name.lower(),
        "from_corpus_version_id": mod_a.version_info.corpus_version_id,
        "to_corpus_version_id": mod_b.version_info.corpus_version_id,
        "severity": severity,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "old_sha256": sha_a,
        "new_sha256": sha_b,
        "changes": changes,
    }


def write_diff(
    rev_a: str | Path,
    rev_b: str | Path,
    output: str | Path,
    *,
    module_id: str | None = None,
) -> dict[str, Any]:
    """Compute the diff and write JSON to ``output``."""
    diff = diff_modules(rev_a, rev_b, module_id=module_id)
    Path(output).write_text(json.dumps(diff, indent=2, sort_keys=True))
    return diff


# ---------------------------------------------------------------------------
# section-level diffs
# ---------------------------------------------------------------------------


def _diff_text(a: GbmModule, b: GbmModule) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    keys = sorted(set(a.text) | set(b.text))
    for key in keys:
        verses_a = a.text.get(key)
        verses_b = b.text.get(key)
        ref = f"{key[0]}.{key[1]}"
        if verses_a is None:
            out.append({"kind": "chapter_added", "ref": ref,
                        "verse_count": len(verses_b or [])})
            continue
        if verses_b is None:
            out.append({"kind": "chapter_removed", "ref": ref,
                        "verse_count": len(verses_a)})
            continue
        if verses_a == verses_b:
            continue
        max_n = max(len(verses_a), len(verses_b))
        for i in range(max_n):
            va = verses_a[i] if i < len(verses_a) else None
            vb = verses_b[i] if i < len(verses_b) else None
            if va == vb:
                continue
            out.append({
                "kind": "verse_changed",
                "ref": f"{ref}:{i + 1}",
                "old_len": len(va) if va is not None else 0,
                "new_len": len(vb) if vb is not None else 0,
            })
    return out


def _diff_backlinks(a: GbmModule, b: GbmModule) -> list[dict[str, Any]]:
    """Compare backlink sets keyed on (target_vri, source_vri)."""

    def _flatten(module: GbmModule) -> dict[tuple[int, int], int]:
        m: dict[tuple[int, int], int] = {}
        for grp in module.backlinks:
            for bl in grp.sources:
                m[(grp.target_vri, bl.source_vri)] = int(bl.verification)
        return m

    map_a = _flatten(a)
    map_b = _flatten(b)
    out: list[dict[str, Any]] = []
    for k in sorted(set(map_a) | set(map_b)):
        sa = map_a.get(k)
        sb = map_b.get(k)
        if sa is None:
            out.append({"kind": "backlink_added",
                        "target_vri": k[0], "source_vri": k[1],
                        "verification": sb})
        elif sb is None:
            out.append({"kind": "backlink_removed",
                        "target_vri": k[0], "source_vri": k[1]})
        elif sa != sb:
            out.append({"kind": "backlink_verification_changed",
                        "target_vri": k[0], "source_vri": k[1],
                        "from": sa, "to": sb})
    return out


def _diff_inline_links(a: GbmModule, b: GbmModule) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    set_a = {(l.source_vri, l.start_offset, l.length, l.target_vri, int(l.kind))
             for l in a.inline_links}
    set_b = {(l.source_vri, l.start_offset, l.length, l.target_vri, int(l.kind))
             for l in b.inline_links}
    for added in sorted(set_b - set_a):
        out.append({"kind": "inline_link_added",
                    "source_vri": added[0], "start_offset": added[1],
                    "length": added[2], "target_vri": added[3],
                    "link_kind": added[4]})
    for removed in sorted(set_a - set_b):
        out.append({"kind": "inline_link_removed",
                    "source_vri": removed[0], "start_offset": removed[1],
                    "length": removed[2], "target_vri": removed[3],
                    "link_kind": removed[4]})
    return out


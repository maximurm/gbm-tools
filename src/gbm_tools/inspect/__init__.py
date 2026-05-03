"""Read-only diagnostic dump tool (Phase B6).

Implements `gbm-inspect`. See GBM_FORMAT_SPEC.md §10.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..formats import GbmReader, decode, read_gbm

_console = Console()


def inspect_file(path: str | Path, *, section: str | None = None,
                 vri: int | None = None) -> int:
    """Pretty-print structural info about a .gbm file. Returns process exit code."""
    p = Path(path)
    size = p.stat().st_size

    with GbmReader(p) as reader:
        _console.print(f"[bold]File:[/bold] {p.name}  ({size:,} bytes)")
        _console.print(
            f"Magic: GBM1  Format: {reader.format_version}  "
            f"SectionIndexVersion: 1"
        )

        if vri is not None:
            return _print_vri(p, vri)

        if section is not None:
            return _print_section(reader, section)

        table = Table(title=f"Sections ({len(reader.section_names)})")
        table.add_column("name", style="cyan")
        table.add_column("attrs", justify="right")
        table.add_column("content (snappy bytes)", justify="right")
        for name in reader.section_names:
            attrs, content = reader.read_section(name)
            table.add_row(name, _summarize_attrs(attrs), str(len(content)))
        _console.print(table)
    return 0


def _print_section(reader: GbmReader, name: str) -> int:
    if not reader.has_section(name):
        _console.print(f"[red]section not found: {name}[/red]")
        return 1
    attrs, content = reader.read_section(name)
    _console.print(f"[bold]Section:[/bold] {name}")
    _console.print(f"  attrs: {attrs}")
    _console.print(f"  decompressed content: {len(content):,} bytes")
    return 0


def _print_vri(path: Path, vri: int) -> int:
    parts = decode(vri)
    module = read_gbm(path)
    key = (parts.book, parts.chapter)
    if key not in module.text:
        _console.print(f"[red]no text for book {parts.book} chapter {parts.chapter}[/red]")
        return 1
    verses = module.text[key]
    if parts.verse < 1 or parts.verse > len(verses):
        _console.print(f"[red]verse {parts.verse} out of range (1..{len(verses)})[/red]")
        return 1
    _console.print(
        f"[bold]VRI 0x{vri:016X}[/bold]  "
        f"corpus={parts.corpus} version={parts.version} "
        f"book={parts.book} ch={parts.chapter} v={parts.verse}"
    )
    _console.print(verses[parts.verse - 1])
    return 0


def _summarize_attrs(attrs: dict[str, object]) -> str:
    return ", ".join(f"{k}={v}" for k, v in attrs.items())


__all__ = ["inspect_file"]

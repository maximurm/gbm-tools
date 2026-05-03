"""CLI entry points for gbm-tools.

Each top-level function corresponds to one console_script in pyproject.toml:
- gbm-convert: extract source format → Markdown directory
- gbm-build:   assemble Markdown directory → .gbm
- gbm-inspect: debug/diagnostic dump of a .gbm file
- gbm-diff:    compare two .gbm revisions
- gbm-test:    run the test fixture pipeline
- gbm-index-parse: parse "Scriptural & Rod Index.txt" → CSV

These are thin Click wrappers around the implementation modules.
"""

from __future__ import annotations

import click

from . import __version__


@click.command(name="gbm-convert")
@click.argument("source", type=click.Path(exists=True))
@click.option("--format", "src_format", required=True,
              type=click.Choice(["rtf", "usfm", "yes2"]),
              help="Source format (rtf is PRIMARY for all corpora; yes2 is legacy)")
@click.option("--output", "-o", required=True, type=click.Path(),
              help="Output directory for Markdown files")
@click.option("--rules", type=click.Path(exists=True),
              help="rules.yaml file (defaults to gbm-content/rules.yaml)")
@click.option("--corpus", type=click.Choice(["bible", "srod", "egw"]),
              help="Target corpus (auto-detected if omitted)")
def convert(source: str, src_format: str, output: str,
            rules: str | None, corpus: str | None) -> None:
    """Convert SOURCE to a Markdown directory at OUTPUT."""
    click.echo(f"gbm-convert {__version__}: {src_format} → {output}")
    click.echo(f"  source: {source}")
    if rules:
        click.echo(f"  rules:  {rules}")
    if corpus:
        click.echo(f"  corpus: {corpus}")
    click.echo("  [stub — implementation in convert/ module]")


@click.command(name="gbm-build")
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--output", "-o", required=True, type=click.Path(),
              help="Output .gbm file path")
@click.option("--corpus", required=True, type=click.Choice(["bible", "srod", "egw"]))
@click.option("--version-id", required=True, type=int,
              help="16-bit version ID (see VRI spec)")
@click.option("--revision", default=1, type=int, help="Module revision number")
def build(source_dir: str, output: str, corpus: str,
          version_id: int, revision: int) -> None:
    """Build .gbm binary from SOURCE_DIR (Markdown layout)."""
    click.echo(f"gbm-build {__version__}: {source_dir} → {output}")
    click.echo(f"  corpus={corpus} version_id={version_id} revision={revision}")
    click.echo("  [stub — implementation in build/ module]")


@click.command(name="gbm-inspect")
@click.argument("gbm_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--section", help="Dump only the named section (e.g., 'text', 'backlinks')")
@click.option("--vri", type=int, help="Inspect a single VRI verse")
def inspect(gbm_file: str, section: str | None, vri: int | None) -> None:
    """Read a .gbm file and dump its structure."""
    from .inspect import inspect_file

    rc = inspect_file(gbm_file, section=section, vri=vri)
    if rc != 0:
        raise SystemExit(rc)


@click.command(name="gbm-diff")
@click.argument("rev_a", type=click.Path(exists=True, dir_okay=False))
@click.argument("rev_b", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", type=click.Path(), help="Errata patch output (.json)")
@click.option("--module-id", help="Module identifier to embed in patch")
def diff(rev_a: str, rev_b: str, output: str | None,
         module_id: str | None) -> None:
    """Compare two .gbm revisions; emit errata patch JSON."""
    import json as _json

    from .diff import diff_modules, write_diff

    if output:
        patch = write_diff(rev_a, rev_b, output, module_id=module_id)
        click.echo(f"gbm-diff {__version__}: wrote {output} "
                   f"(severity={patch['severity']}, "
                   f"{len(patch['changes'])} change(s))")
    else:
        patch = diff_modules(rev_a, rev_b, module_id=module_id)
        click.echo(_json.dumps(patch, indent=2, sort_keys=True))


@click.command(name="gbm-test")
def test() -> None:
    """Run the bundled fixture round-trip test."""
    click.echo(f"gbm-test {__version__}: running fixture pipeline")
    click.echo("  [stub — runs tests/fixtures pipeline]")


@click.command(name="gbm-index-parse")
@click.argument("index_txt", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", required=True, type=click.Path(),
              help="Output CSV path")
def index_parse(index_txt: str, output: str) -> None:
    """Parse 'Scriptural & Rod Index.txt' → CSV of (book, ch, v, target)."""
    click.echo(f"gbm-index-parse {__version__}: {index_txt} → {output}")
    click.echo("  [stub — implementation in convert/index_parser.py]")

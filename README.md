# gbm-tools

Converter and builder CLI for `.gbm` Bible / literature modules.

Part of the GADSDA Bible app ecosystem. The `.gbm` format is the binary
distribution format used by goldenBowl (web), Biblary (Android), and
Alkitab (iOS). See the parent project for full architecture:

- Architecture: <https://github.com/maximurm/goldenBowlWeb/blob/master/docs/workspace/ARCHITECTURE_DECISIONS.md>
- Format spec:  <https://github.com/maximurm/goldenBowlWeb/blob/master/docs/workspace/GBM_FORMAT_SPEC.md>
- Pipeline:     <https://github.com/maximurm/goldenBowlWeb/blob/master/docs/workspace/CONTENT_PIPELINE.md>

## Status

🚧 Phase A — package scaffolded; CLI entry points are stubs.
Implementation is tracked in `maximurm/goldenBowlWeb` issues #116–#180.

## CLI

| Command | Purpose | Phase |
|---|---|---|
| `gbm-convert` | Source format → Markdown directory | B/C |
| `gbm-build` | Markdown directory → `.gbm` binary | B |
| `gbm-inspect` | Read-only `.gbm` debug dump | B6 |
| `gbm-diff` | Compare two `.gbm` revisions | C6 |
| `gbm-index-parse` | Parse "Scriptural & Rod Index.txt" → CSV | E1 |
| `gbm-test` | Round-trip fixture test | dev |

The **RTF format is the PRIMARY content path** for all corpora (Bible,
SRod, EGW). YES2 extraction is preserved as legacy / spot-check tooling.

## Install (development)

```bash
git clone https://github.com/maximurm/gbm-tools.git
cd gbm-tools
python -m pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE) (TBD).

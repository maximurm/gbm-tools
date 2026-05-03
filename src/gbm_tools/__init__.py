"""gbm-tools — converter and builder CLI for .gbm modules.

Public API exposes the major pipeline stages:
- formats: VRI utility, gbm reader/writer
- convert: format-specific extractors (RTF primary, USFM, YES2 legacy)
- build: assemble Markdown directories into .gbm binaries
- inspect: read-only debug tooling
- diff: two-revision comparator
"""

__version__ = "0.1.0"

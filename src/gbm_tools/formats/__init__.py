"""Binary format readers/writers and VRI encoding."""

from .vri import (
    CORPUS_BIBLE,
    CORPUS_EGW,
    CORPUS_SROD,
    CORPUS_UNKNOWN,
    VriParts,
    decode,
    encode,
    encode_from_ari,
    to_ari,
)

__all__ = [
    "CORPUS_BIBLE",
    "CORPUS_EGW",
    "CORPUS_SROD",
    "CORPUS_UNKNOWN",
    "VriParts",
    "decode",
    "encode",
    "encode_from_ari",
    "to_ari",
]

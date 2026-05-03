"""Bintex value-map encoder/decoder.

Bintex is the small typed-value scheme used by YES2 and inherited by GBM for
section attribute headers. We implement only the subset GBM uses:

- valueSimpleMap: a flat string-keyed map whose values are one of:
    * uint8/16/32/64
    * int32 (signed)
    * utf8 string (uint16 length-prefixed)

Wire format (matches YES2 BintexReader for byte-level interop on shared keys):

    uint8   entry_count
    repeat entry_count times:
        uint8   key_len
        key_len bytes  key (ASCII)
        uint8   type_tag
        payload (type-dependent)

Type tags:
    0x01  uint8   (1 byte)
    0x02  uint16  (2 bytes, big-endian)
    0x03  uint32  (4 bytes, big-endian)
    0x04  int32   (4 bytes, big-endian, signed two's complement)
    0x05  uint64  (8 bytes, big-endian)
    0x10  utf8    (uint16 length-prefixed, big-endian length)

This is intentionally minimal — additions require a synchronized PR across
gbm-tools and every reader that consumes attribute maps.
"""

from __future__ import annotations

import struct
from typing import Union

Value = Union[int, str]

TAG_U8 = 0x01
TAG_U16 = 0x02
TAG_U32 = 0x03
TAG_I32 = 0x04
TAG_U64 = 0x05
TAG_UTF8 = 0x10


def encode_value_map(items: dict[str, Value]) -> bytes:
    """Encode a dict to a bintex valueSimpleMap byte string."""
    if len(items) > 0xFF:
        raise ValueError(f"value map has too many entries: {len(items)} (max 255)")
    out = bytearray()
    out.append(len(items))
    for key, value in items.items():
        key_bytes = key.encode("ascii")
        if len(key_bytes) > 0xFF:
            raise ValueError(f"key too long: {key!r}")
        out.append(len(key_bytes))
        out.extend(key_bytes)
        out.extend(_encode_value(value))
    return bytes(out)


def decode_value_map(data: bytes) -> dict[str, Value]:
    """Decode a bintex valueSimpleMap byte string to a dict."""
    pos = 0
    if len(data) < 1:
        raise ValueError("value map data is empty")
    count = data[pos]
    pos += 1
    out: dict[str, Value] = {}
    for _ in range(count):
        if pos >= len(data):
            raise ValueError("truncated value map (key length)")
        key_len = data[pos]
        pos += 1
        key = data[pos : pos + key_len].decode("ascii")
        pos += key_len
        if pos >= len(data):
            raise ValueError("truncated value map (type tag)")
        tag = data[pos]
        pos += 1
        value, pos = _decode_value(tag, data, pos)
        out[key] = value
    return out


def _encode_value(value: Value) -> bytes:
    if isinstance(value, bool):  # bool is int — explicit guard
        raise TypeError("bool not supported in bintex value map")
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) > 0xFFFF:
            raise ValueError(f"utf8 value too long: {len(encoded)} bytes")
        return bytes([TAG_UTF8]) + struct.pack(">H", len(encoded)) + encoded
    if isinstance(value, int):
        if 0 <= value <= 0xFF:
            return bytes([TAG_U8, value])
        if 0 <= value <= 0xFFFF:
            return bytes([TAG_U16]) + struct.pack(">H", value)
        if 0 <= value <= 0xFFFFFFFF:
            return bytes([TAG_U32]) + struct.pack(">I", value)
        if -0x80000000 <= value < 0:
            return bytes([TAG_I32]) + struct.pack(">i", value)
        if 0 <= value <= 0xFFFFFFFFFFFFFFFF:
            return bytes([TAG_U64]) + struct.pack(">Q", value)
        raise ValueError(f"integer out of supported bintex range: {value}")
    raise TypeError(f"unsupported bintex value type: {type(value).__name__}")


def _decode_value(tag: int, data: bytes, pos: int) -> tuple[Value, int]:
    if tag == TAG_U8:
        return data[pos], pos + 1
    if tag == TAG_U16:
        return struct.unpack(">H", data[pos : pos + 2])[0], pos + 2
    if tag == TAG_U32:
        return struct.unpack(">I", data[pos : pos + 4])[0], pos + 4
    if tag == TAG_I32:
        return struct.unpack(">i", data[pos : pos + 4])[0], pos + 4
    if tag == TAG_U64:
        return struct.unpack(">Q", data[pos : pos + 8])[0], pos + 8
    if tag == TAG_UTF8:
        length = struct.unpack(">H", data[pos : pos + 2])[0]
        pos += 2
        return data[pos : pos + length].decode("utf-8"), pos + length
    raise ValueError(f"unknown bintex type tag: 0x{tag:02x}")

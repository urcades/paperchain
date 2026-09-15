"""Parse and normalize JSON through the portable binary64 numeric profile.

All JSON numbers are rounded exactly as IEEE-754 binary64 values. A rounded
integral value is returned as :class:`int` only when it lies in the inclusive
range ``-(2**53 - 1)`` through ``2**53 - 1``; ordinary fractions remain
:class:`float`. Binary64 underflow to zero is allowed, and negative zero
normalizes to integer zero, so both compare with the profile's zero semantics.

JSON numbers cannot carry exact arbitrary-precision decimal data in this
profile. Encode such values as JSON strings and decode those strings with an
appropriate decimal or application-specific parser after transport.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

MAX_PORTABLE_INTEGER = 9_007_199_254_740_991

__all__ = [
    "MAX_PORTABLE_INTEGER",
    "PortableJSONError",
    "loads_portable_json",
    "normalize_portable_json",
    "parse_portable_number",
]

_JSON_NUMBER = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z",
    re.ASCII,
)
_SIMPLE_PATH_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
_EXACT_DECIMAL_GUIDANCE = (
    "encode exact decimal values as JSON strings and decode them separately"
)


class PortableJSONError(ValueError):
    """The source or value is outside the portable JSON profile."""


class _NumberToken(str):
    """A JSON numeric token retained until its structural path is known."""


class _NonFiniteToken(str):
    """A non-standard JSON constant retained for a path-aware error."""


class _ObjectPairs:
    """Object members retained in order so duplicate names remain visible."""

    __slots__ = ("pairs",)

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        self.pairs = pairs


def _number_at_path(token: str, path: str | None) -> int | float:
    location = f" at {path}" if path is not None else ""
    if _JSON_NUMBER.fullmatch(token) is None:
        raise PortableJSONError(f"invalid JSON number{location}: {token!r}")

    try:
        number = float(token)
    except (OverflowError, ValueError) as error:
        raise PortableJSONError(
            f"invalid JSON number{location}: {token!r}"
        ) from error

    if not math.isfinite(number):
        raise PortableJSONError(
            f"JSON number{location} overflows binary64: {token!r}; "
            f"{_EXACT_DECIMAL_GUIDANCE}"
        )

    if number.is_integer():
        if abs(number) > MAX_PORTABLE_INTEGER:
            raise PortableJSONError(
                f"integral JSON number{location} is outside the portable range: "
                f"{token!r}; {_EXACT_DECIMAL_GUIDANCE}"
            )
        # This intentionally maps both +0 and -0 to the same portable value.
        return int(number)

    return number


def parse_portable_number(token: str) -> int | float:
    """Normalize one raw JSON number token through IEEE-754 binary64.

    This function is suitable for both ``json.loads(parse_int=...)`` and
    ``json.loads(parse_float=...)``. Finite binary64 underflow to zero is
    allowed. Integral results outside ``+/- (2**53 - 1)`` are rejected.

    Values requiring an exact decimal representation should be encoded as JSON
    strings, then decoded separately with :mod:`decimal` or a domain parser.
    """

    if type(token) is not str:
        raise PortableJSONError("a raw JSON number token must be a string")
    return _number_at_path(token, None)


def _path_for_key(path: str, key: str) -> str:
    if _SIMPLE_PATH_KEY.fullmatch(key) is not None:
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key, ensure_ascii=True)}]"


def _normalize(value: Any, path: str, active: set[int]) -> Any:
    # bool is an int subclass in Python, so it must be handled first.
    if value is None or type(value) is bool or type(value) is str:
        return value

    if type(value) is _NumberToken:
        return _number_at_path(value, path)

    if type(value) is _NonFiniteToken:
        raise PortableJSONError(f"nonfinite JSON number at {path}: {value}")

    if type(value) is int:
        try:
            binary64 = float(value)
        except OverflowError as error:
            raise PortableJSONError(
                f"integral value at {path} overflows binary64; "
                f"{_EXACT_DECIMAL_GUIDANCE}"
            ) from error
        if not math.isfinite(binary64) or abs(binary64) > MAX_PORTABLE_INTEGER:
            raise PortableJSONError(
                f"integral value at {path} is outside the portable range; "
                f"{_EXACT_DECIMAL_GUIDANCE}"
            )
        return int(binary64)

    if type(value) is float:
        if not math.isfinite(value):
            raise PortableJSONError(f"nonfinite number at {path}")
        if value.is_integer():
            if abs(value) > MAX_PORTABLE_INTEGER:
                raise PortableJSONError(
                    f"integral value at {path} is outside the portable range; "
                    f"{_EXACT_DECIMAL_GUIDANCE}"
                )
            return int(value)
        return value

    if type(value) is _ObjectPairs:
        identity = id(value)
        if identity in active:
            raise PortableJSONError(f"container cycle at {path}")
        active.add(identity)
        try:
            result: dict[str, Any] = {}
            for key, item in value.pairs:
                if key in result:
                    raise PortableJSONError(f"{path}: duplicate object key {key!r}")
                result[key] = _normalize(item, _path_for_key(path, key), active)
            return result
        finally:
            active.remove(identity)

    if type(value) is list:
        identity = id(value)
        if identity in active:
            raise PortableJSONError(f"container cycle at {path}")
        active.add(identity)
        try:
            return [
                _normalize(item, f"{path}[{index}]", active)
                for index, item in enumerate(value)
            ]
        finally:
            active.remove(identity)

    if type(value) is dict:
        identity = id(value)
        if identity in active:
            raise PortableJSONError(f"container cycle at {path}")
        active.add(identity)
        try:
            result = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise PortableJSONError(
                        f"object key at {path} must be a string, got "
                        f"{type(key).__name__}"
                    )
                result[key] = _normalize(item, _path_for_key(path, key), active)
            return result
        finally:
            active.remove(identity)

    raise PortableJSONError(
        f"value at {path} is not JSON-compatible: {type(value).__name__}"
    )


def normalize_portable_json(value: Any) -> Any:
    """Return a normalized portable-JSON copy of an already-parsed value.

    The traversal distinguishes booleans from integers, rejects Python-only
    values, reports nested JSON-style paths, and detects container cycles.
    Exact decimal data should enter this function as strings.
    """

    try:
        return _normalize(value, "$", set())
    except RecursionError as error:
        raise PortableJSONError("JSON value nesting is too deep") from error


def loads_portable_json(source: str | bytes | bytearray) -> Any:
    """Parse raw JSON and return a value normalized to portable binary64 rules.

    Duplicate object keys, nonfinite constants, binary64 overflow, and unsafe
    integral results are rejected. Numeric tokens are retained until traversal
    so errors can name their nested path. Binary64 underflow to zero is valid.

    Store numbers as JSON strings when their exact decimal spelling or precision
    matters, then decode those strings separately after this transport step.
    """

    if type(source) not in (str, bytes, bytearray):
        raise PortableJSONError("raw JSON source must be str, bytes, or bytearray")

    try:
        decoded = json.loads(
            source,
            parse_int=_NumberToken,
            parse_float=_NumberToken,
            parse_constant=_NonFiniteToken,
            object_pairs_hook=_ObjectPairs,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise PortableJSONError(f"invalid JSON source: {error}") from error

    return normalize_portable_json(decoded)

"""A root ``.env`` read as python-dotenv reads it, without depending on it: the value a
maker's Widget got on their machine is the value the command sends."""
from __future__ import annotations

import codecs
import re

_SPACE = re.compile(r"\s*", re.MULTILINE)
_EXPORT = re.compile(r"(?:export[^\S\r\n]+)?")
_QUOTED_KEY = re.compile(r"'([^']+)'")
_KEY = re.compile(r"([^=\#\s]+)")
_BLANK = re.compile(r"[^\S\r\n]*")
_EQUALS = re.compile(r"=[^\S\r\n]*")
_SINGLE = re.compile(r"'((?:\\'|[^'])*)'")
_DOUBLE = re.compile(r'"((?:\\"|[^"])*)"')
_PLAIN = re.compile(r"([^\r\n]*)")
_COMMENT = re.compile(r"(?:[^\S\r\n]*#[^\r\n]*)?")
_END = re.compile(r"[^\S\r\n]*(?:\r\n|\n|\r|$)")
_REST = re.compile(r"[^\r\n]*(?:\r|\n|\r\n)?")
_SINGLE_ESCAPES = re.compile(r"\\[\\']")
_DOUBLE_ESCAPES = re.compile(r"\\[\\'\"abfnrtv]")


class _Unread(Exception):
    """A line python-dotenv skips, as it cannot read it."""


def parse_env(text: str) -> dict[str, str]:
    """Each name of a ``.env`` and its value, as python-dotenv's parser gives them: quotes
    and a comment removed, a double-quoted value's escapes decoded, a single-quoted one's
    kept but for ``\\\\`` and ``\\'``. A line it cannot read is left out, a later line
    wins, and a name without ``=`` unsets it. A ``${NAME}`` is kept as written."""
    values: dict[str, str] = {}
    at = 0

    def read(regex: re.Pattern[str]) -> re.Match[str]:
        nonlocal at
        match = regex.match(text, at)
        if match is None:
            raise _Unread
        at = match.end()
        return match

    while at < len(text):
        read(_SPACE)
        if at == len(text):
            break
        try:
            read(_EXPORT)
            key = None if text.startswith("#", at) else read(_QUOTED_KEY if text.startswith("'", at) else _KEY).group(1)
            read(_BLANK)
            value = None
            if text.startswith("=", at):
                read(_EQUALS)
                first = text[at : at + 1]
                if first == "'":
                    value = _decode(_SINGLE_ESCAPES, read(_SINGLE).group(1))
                elif first == '"':
                    value = _decode(_DOUBLE_ESCAPES, read(_DOUBLE).group(1))
                elif first in ("", "\n", "\r"):
                    value = ""
                else:
                    value = re.sub(r"\s+#.*", "", read(_PLAIN).group(1)).rstrip()
            read(_COMMENT)
            read(_END)
        except _Unread:
            read(_REST)
            continue
        if key is not None and value is not None:
            values[key] = value
        elif key is not None:
            values.pop(key, None)
    return values


def _decode(escapes: re.Pattern[str], value: str) -> str:
    return escapes.sub(lambda match: codecs.decode(match.group(0), "unicode-escape"), value)
